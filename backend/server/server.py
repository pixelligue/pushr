import asyncio
import os
import uuid
import sys
import subprocess
import traceback
import logging
from typing import Dict, Optional, List

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("browser-api")

try:
    from browser_use import Agent, Browser, BrowserConfig
    from browser_use.agent.views import AgentHistoryList, ActionResult
    browser_use_available = True
except ImportError as e:
    logger.error(f"Ошибка импорта browser_use: {str(e)}")
    browser_use_available = False

from response_formatter import format_results

if sys.platform == 'win32':
    loop = asyncio.ProactorEventLoop()
    asyncio.set_event_loop(loop)
    logger.info("Настроен ProactorEventLoop для Windows")

    try:
        import nest_asyncio
        nest_asyncio.apply()
        logger.info("Применена поддержка вложенных циклов с nest_asyncio")
    except ImportError:
        logger.warning("nest_asyncio не установлен")

load_dotenv()

async def check_chrome_cdp_available(cdp_url="http://localhost:9222"):
    try:
        import httpx
        response = await httpx.get(f"{cdp_url}/json/version", timeout=2)
        if response.status_code == 200:
            logger.info(f"Chrome CDP доступен по адресу {cdp_url}")
            return True
        else:
            logger.warning(f"Chrome CDP недоступен по адресу {cdp_url}")
            return False
    except Exception as e:
        logger.warning(f"Не удалось подключиться к Chrome CDP: {str(e)}")
        return False

app = FastAPI(title="Browser Automation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TaskRequest(BaseModel):
    task: str
    model: str = "gpt-4.1-nano-2025-04-14"
    provider: str = "openai"
    headless: bool = False
    max_steps: int = 5
    use_vision: bool = True

class TaskResponse(BaseModel):
    task_id: str
    status: str = "started"
    message: str = "Task started"

class TaskResult(BaseModel):
    task_id: str
    status: str
    steps: int = 0
    results: List[Dict] = Field(default_factory=list)
    error: Optional[str] = None

class RunRequest(BaseModel):
    task: str
    model: str = "gpt-4.1-nano-2025-04-14"
    provider: str = "openai"
    headless: bool = True
    max_steps: int = 5

class RunResponse(BaseModel):
    result: str

tasks: Dict[str, TaskResult] = {}
browsers: Dict[str, Browser] = {}
agents: Dict[str, Agent] = {}

def get_llm(provider: str, model: str):
    try:
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set")
            return ChatOpenAI(model=model, temperature=0.0)
        
        elif provider == "azure":
            api_key = os.getenv("AZURE_OPENAI_KEY")
            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            if not api_key or not endpoint:
                raise ValueError("AZURE_OPENAI_KEY или AZURE_OPENAI_ENDPOINT не установлены")
            deployment_name = model
            return AzureChatOpenAI(
                deployment_name=deployment_name,
                openai_api_version="2025-04-14",
                azure_endpoint=endpoint,
                api_key=api_key,
                temperature=0.0
            )
        
        elif provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not set")
            return ChatAnthropic(model=model, temperature=0.0)
        
        elif provider == "google":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY not set")
            return ChatGoogleGenerativeAI(model=model, temperature=0.0)
        
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    except Exception as e:
        logger.error(f"Ошибка при получении LLM модели: {str(e)}")
        raise

async def run_browser_task(task_id: str, task_request: TaskRequest):
    try:
        logger.info(f"Запуск задачи {task_id} с параметрами: {task_request}")
        
        cdp_url = os.getenv("BROWSER_CDP_URL", "http://localhost:9222")
        
        logger.info("Инициализация браузера с CDP")
        browser_config = BrowserConfig(
            headless=task_request.headless,
            cdp_url=cdp_url
        )
        
        browser = Browser(config=browser_config)
        browsers[task_id] = browser
        
        logger.info(f"Получение LLM модели: provider={task_request.provider}, model={task_request.model}")
        llm = get_llm(task_request.provider, task_request.model)
        
        logger.info(f"Инициализация агента для задачи: {task_request.task}")
        agent = Agent(
            task=task_request.task,
            llm=llm,
            browser=browser,
            use_vision=task_request.use_vision,
        )
        agents[task_id] = agent
        
        tasks[task_id].status = "running"
        logger.info(f"Задача {task_id} запущена")
        
        history: AgentHistoryList = await agent.run(max_steps=task_request.max_steps)
        logger.info(f"Задача {task_id} выполнена, шагов: {len(history.history)}")
        
        results = []
        for history_item in history.history:
            step_results = {}
            if history_item.result:
                for result in history_item.result:
                    if isinstance(result, ActionResult) and result.extracted_content:
                        step_results["content"] = result.extracted_content
                    if isinstance(result, ActionResult) and result.error:
                        step_results["error"] = result.error
            
            if history_item.state:
                step_results["url"] = history_item.state.url
                step_results["title"] = history_item.state.title
            
            if step_results.get("content"):
                step_results["content"] = format_results(step_results["content"])
            
            results.append(step_results)
        
        tasks[task_id].results = results
        tasks[task_id].steps = len(history.history)
        tasks[task_id].status = "completed"
        logger.info(f"Задача {task_id} завершена успешно")
        
    except Exception as e:
        logger.error(f"Ошибка при выполнении задачи {task_id}: {str(e)}")
        logger.error(traceback.format_exc())
        tasks[task_id].status = "failed"
        tasks[task_id].error = str(e)
    
    finally:
        if task_id in browsers:
            logger.info(f"Закрытие браузера для задачи {task_id}")
            try:
                await browsers[task_id].close()
            except Exception as e:
                logger.error(f"Ошибка при закрытии браузера: {str(e)}")
            del browsers[task_id]
        
        if task_id in agents:
            del agents[task_id]

@app.post("/task", response_model=TaskResponse)
async def create_task(task_request: TaskRequest, background_tasks: BackgroundTasks):
    try:
        if not browser_use_available:
            logger.error("browser_use недоступен")
            raise HTTPException(
                status_code=500, 
                detail="Библиотека browser_use не установлена"
            )
        
        task_id = str(uuid.uuid4())
        logger.info(f"Создание новой задачи с ID: {task_id}")
        
        tasks[task_id] = TaskResult(
            task_id=task_id,
            status="starting",
        )
        
        background_tasks.add_task(run_browser_task, task_id, task_request)
        logger.info(f"Задача {task_id} поставлена в очередь")
        
        return TaskResponse(task_id=task_id)
    except Exception as e:
        logger.error(f"Ошибка при создании задачи: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при создании задачи: {str(e)}"
        )

@app.get("/task/{task_id}", response_model=TaskResult)
async def get_task_status(task_id: str):
    if task_id not in tasks:
        logger.warning(f"Запрос статуса несуществующей задачи: {task_id}")
        raise HTTPException(status_code=404, detail="Task not found")
    
    logger.info(f"Запрос статуса задачи {task_id}: {tasks[task_id].status}")
    return tasks[task_id]

@app.delete("/task/{task_id}")
async def cancel_task(task_id: str):
    if task_id not in tasks:
        logger.warning(f"Попытка отмены несуществующей задачи: {task_id}")
        raise HTTPException(status_code=404, detail="Task not found")
    
    logger.info(f"Отмена задачи {task_id}")
    
    if task_id in agents:
        logger.info(f"Остановка агента для задачи {task_id}")
        agents[task_id].stop()
    
    if task_id in browsers:
        logger.info(f"Закрытие браузера для задачи {task_id}")
        try:
            await browsers[task_id].close()
        except Exception as e:
            logger.error(f"Ошибка при закрытии браузера: {str(e)}")
        del browsers[task_id]
    
    if task_id in agents:
        del agents[task_id]
    
    tasks[task_id].status = "cancelled"
    logger.info(f"Задача {task_id} отменена")
    
    return {"status": "cancelled", "task_id": task_id}

@app.post("/run", response_model=RunResponse)
async def run_task(request: RunRequest):
    logger.info(f"Запрос на выполнение задачи: {request.task}")
    
    if not browser_use_available:
        logger.error("browser_use недоступен")
        return RunResponse(result="Ошибка: Библиотека browser_use не установлена")
    
    try:
        cdp_url = os.getenv("BROWSER_CDP_URL", "http://localhost:9222")
        
        logger.info("Инициализация браузера с CDP")
        browser_config = BrowserConfig(
            headless=request.headless,
            cdp_url=cdp_url
        )
        
        browser = Browser(config=browser_config)
        
        logger.info(f"Получение LLM модели: provider={request.provider}, model={request.model}")
        llm = get_llm(request.provider, request.model)
        
        logger.info(f"Инициализация агента для задачи: {request.task}")
        agent = Agent(
            task=request.task,
            llm=llm,
            browser=browser,
        )
        
        logger.info("Запуск агента")
        history: AgentHistoryList = await agent.run(max_steps=request.max_steps)
        logger.info(f"Задача выполнена, шагов: {len(history.history)}")
        
        extracted_content = ""
        for history_item in history.history:
            if history_item.result:
                for result in history_item.result:
                    if isinstance(result, ActionResult) and result.extracted_content:
                        extracted_content += result.extracted_content + "\n\n"
        
        formatted_result = format_results(extracted_content) if extracted_content else "Задача выполнена без результатов"
        
        logger.info("Закрытие браузера")
        try:
            await browser.close()
        except Exception as e:
            logger.error(f"Ошибка при закрытии браузера: {str(e)}")
        
        return RunResponse(result=formatted_result)
    
    except Exception as e:
        logger.error(f"Ошибка при выполнении задачи: {str(e)}")
        logger.error(traceback.format_exc())
        return RunResponse(result=f"Ошибка при выполнении задачи: {str(e)}")

@app.get("/status")
async def check_status():
    try:
        cdp_url = os.getenv("BROWSER_CDP_URL", "http://localhost:9222")
        cdp_available = await check_chrome_cdp_available(cdp_url)
        
        status = {
            "server": "ok",
            "browser_use_available": browser_use_available,
            "cdp_url": cdp_url,
            "cdp_connection": "ok" if cdp_available else "not available",
            "platform": sys.platform
        }
        
        return status
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса: {str(e)}")
        return {"server": "error", "error": str(e)}

@app.get("/launch-chrome")
async def launch_chrome():
    try:
        chrome_path = os.getenv("CHROMIUM_PATH", None)
        if not chrome_path:
            if sys.platform == 'win32':
                possible_paths = [
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
                ]
                for path in possible_paths:
                    if os.path.exists(path):
                        chrome_path = path
                        break
            elif sys.platform == 'darwin':
                chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            else:
                try:
                    chrome_path = subprocess.check_output(["which", "google-chrome"]).decode("utf-8").strip()
                except:
                    try:
                        chrome_path = subprocess.check_output(["which", "chrome"]).decode("utf-8").strip()
                    except:
                        pass
        
        if not chrome_path:
            return {"status": "error", "message": "Путь к Chrome не найден. Укажите CHROMIUM_PATH в .env"}
        
        cdp_port = os.getenv("CHROME_REMOTE_DEBUGGING_PORT", "9222")
        cdp_url = f"http://localhost:{cdp_port}"
        if await check_chrome_cdp_available(cdp_url):
            return {"status": "ok", "message": f"Chrome уже запущен и доступен по {cdp_url}"}
        
        user_data_dir = os.path.join(os.path.expanduser("~"), "chrome-debug-profile")
        os.makedirs(user_data_dir, exist_ok=True)
        
        cmd = [
            chrome_path,
            f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check"
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False
        )
        
        attempts = 0
        while attempts < 10:
            if await check_chrome_cdp_available(cdp_url):
                return {"status": "ok", "message": f"Chrome запущен успешно. Доступен по {cdp_url}", "pid": process.pid}
            await asyncio.sleep(1)
            attempts += 1
        
        return {"status": "error", "message": "Chrome запущен, но не отвечает по CDP"}
        
    except Exception as e:
        logger.error(f"Ошибка при запуске Chrome: {str(e)}")
        logger.error(traceback.format_exc())
        return {"status": "error", "error": str(e)}

async def init_server():
    cdp_url = os.getenv("BROWSER_CDP_URL", "http://localhost:9222")
    if not await check_chrome_cdp_available(cdp_url):
        logger.warning(f"Chrome CDP недоступен по адресу {cdp_url}")
        logger.warning("Пытаемся автоматически запустить Chrome...")
        
        chrome_result = await launch_chrome()
        if chrome_result.get("status") == "ok":
            logger.info(f"Chrome успешно запущен: {chrome_result.get('message')}")
        else:
            logger.warning(f"Не удалось автоматически запустить Chrome: {chrome_result.get('message', 'Неизвестная ошибка')}")
            logger.warning("Для запуска Chrome вручную выполните команду:")
            logger.warning("chrome.exe --remote-debugging-port=9222 --user-data-dir=remote-profile")
    else:
        logger.info(f"Chrome CDP доступен по адресу {cdp_url}")

async def async_run_server():
    await init_server()
    
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Запуск сервера на {host}:{port}")
    
    config = uvicorn.Config(
        "server:app",
        host=host,
        port=port,
        reload=True,
    )
    server = uvicorn.Server(config)
    await server.serve()

def run_server():
    if sys.platform == 'win32':
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_event_loop()
    
    try:
        loop.run_until_complete(async_run_server())
    except KeyboardInterrupt:
        logger.info("Сервер остановлен пользователем")
    finally:
        loop.close()

if __name__ == "__main__":
    run_server()