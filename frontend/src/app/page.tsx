"use client";
import { useState, useRef, useEffect } from "react";
import { BrowserAgentService } from "./utils/browserAgentService";

// Типы сообщений
type MessageType = 'user' | 'assistant' | 'system';

// Интерфейс сообщения
interface Message {
  type: MessageType;
  content: string;
  timestamp: Date;
  id: string;
}

export default function Home() {
  const [task, setTask] = useState("");
  const [messages, setMessages] = useState<Message[]>([]); 
  const [loading, setLoading] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [showBrowser, setShowBrowser] = useState(false);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Прокрутка вниз при новых сообщениях
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Добавление сообщения в чат
  const addMessage = (content: string, type: MessageType) => {
    const id = `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    setMessages(prev => [...prev, {
      type,
      content,
      timestamp: new Date(),
      id
    }]);
    return id;
  };

  // Удаление сообщения по ID
  const removeMessage = (id: string) => {
    setMessages(prev => prev.filter(msg => msg.id !== id));
  };

  // Выполнение задачи (без видимого браузера)
  const handleRun = async () => {
    if (!task.trim()) return;
    
    // Добавляем сообщение пользователя
    addMessage(task, 'user');
    
    setLoading(true);
    
    // Добавляем сообщение о начале выполнения и сохраняем его ID
    const loadingMsgId = addMessage("Выполняю задачу...", 'system');
    
    try {
      // Используем сервис для выполнения задачи
      const result = await BrowserAgentService.runTask(task, !showBrowser);
      
      // Удаляем сообщение о загрузке
      removeMessage(loadingMsgId);
      
      // Добавляем ответ от ассистента
      addMessage(result, 'assistant');
      
      // Очищаем поле ввода
      setTask("");
    } catch (error) {
      console.error("Ошибка:", error);
      // Удаляем сообщение о загрузке
      removeMessage(loadingMsgId);
      // Добавляем сообщение об ошибке
      addMessage("Ошибка при выполнении задачи", 'system');
    } finally {
      setLoading(false);
    }
  };

  // Запуск задачи с видимым браузером
  const handleRunWithVisibleBrowser = async () => {
    if (!task.trim()) return;
    
    // Добавляем сообщение пользователя
    addMessage(task, 'user');
    
    setLoading(true);
    
    // Добавляем сообщение о начале выполнения и сохраняем его ID
    const loadingMsgId = addMessage("Открываю браузер и выполняю задачу...", 'system');
    
    try {
      // Используем сервис для создания задачи
      const newTaskId = await BrowserAgentService.createTask(task, false, { max_steps: 5 });
      setTaskId(newTaskId);
      
      // Запускаем интервал для проверки статуса
      const interval = setInterval(async () => {
        try {
          // Получаем статус задачи
          const taskResult = await BrowserAgentService.getTaskStatus(newTaskId);
          
          if (taskResult.status === "completed" || taskResult.status === "failed") {
            clearInterval(interval);
            
            // Удаляем сообщение о загрузке
            removeMessage(loadingMsgId);
            
            // Комбинируем результаты всех шагов
            const combinedResult = BrowserAgentService.combineResults(taskResult.results);
            
            // Добавляем ответ от ассистента
            addMessage(combinedResult || taskResult.error || "Задача выполнена без результатов", 'assistant');
            
            setLoading(false);
            setTaskId(null);
            // Очищаем поле ввода
            setTask("");
          }
        } catch (e) {
          console.error("Ошибка при проверке статуса:", e);
          clearInterval(interval);
          // Удаляем сообщение о загрузке
          removeMessage(loadingMsgId);
          addMessage("Ошибка при проверке статуса задачи", 'system');
          setLoading(false);
          setTaskId(null);
        }
      }, 2000); // Проверка каждые 2 секунды
      
    } catch (error) {
      console.error("Ошибка:", error);
      // Удаляем сообщение о загрузке
      removeMessage(loadingMsgId);
      addMessage("Ошибка при запуске задачи", 'system');
      setLoading(false);
    }
  };

  // Отмена задачи
  const handleCancel = async () => {
    if (!taskId) return;
    
    try {
      // Используем сервис для отмены задачи
      await BrowserAgentService.cancelTask(taskId);
      addMessage("Задача отменена", 'system');
      setTaskId(null);
      setLoading(false);
    } catch (error) {
      console.error("Ошибка при отмене задачи:", error);
      addMessage("Ошибка при отмене задачи", 'system');
    }
  };

  // Обработка нажатия Enter для отправки
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      
      // В зависимости от настройки использовать видимый браузер или нет
      if (showBrowser) {
        handleRunWithVisibleBrowser();
      } else {
        handleRun();
      }
    }
  };

  // Переключение режима браузера
  const toggleBrowserMode = () => {
    setShowBrowser(!showBrowser);
  };

  return (
    <div className="min-h-screen bg-black text-white flex flex-col">
      <div className="max-w-4xl mx-auto p-4 md:p-8 w-full flex-1 flex flex-col">
        {/* Область чата */}
        <div className="flex-1 overflow-auto mb-4 space-y-4">
          {messages.map((message, index) => (
            <div 
              key={message.id} 
              className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div className={`max-w-[80%] ${
                message.type === 'system' ? 'text-gray-400 text-sm italic py-1' : 'py-1'
              }`}>
                {message.type === 'assistant' ? (
                  <div className="whitespace-pre-wrap text-gray-300">{message.content}</div>
                ) : (
                  <p>{message.content}</p>
                )}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
        
        {/* Панель ввода */}
        <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3 mb-3">
          <textarea
            className="w-full bg-transparent border-none text-white text-base resize-none focus:outline-none placeholder-gray-500 min-h-[60px]"
            value={task}
            onChange={(e) => setTask(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Опиши задачу для браузера..."
            disabled={loading}
            rows={1}
          />
          
          <div className="flex justify-between items-center mt-2">
            <div className="text-xs text-gray-500">
              {loading ? "Выполняется..." : "Нажмите Enter для отправки"}
            </div>
            
            <div className="flex gap-2 items-center">
              {/* Переключатель режима браузера */}
              <button
                className={`p-2 rounded-lg border ${
                  showBrowser 
                    ? 'bg-zinc-700 border-zinc-600 text-white' 
                    : 'bg-zinc-800 border-zinc-700 text-gray-400'
                }`}
                onClick={toggleBrowserMode}
                title={showBrowser ? "Режим с видимым браузером" : "Режим без видимого браузера"}
              >
                {/* Иконка браузера */}
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
                  <path d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8zm7.5-6.923c-.67.204-1.335.82-1.887 1.855-.143.268-.276.52-.395.773.705.15 1.5.32 2.282.45V1.077zM4.249 3.539c.142-.384.304-.744.481-1.078a6.7 6.7 0 0 1 .597-.933A7.01 7.01 0 0 0 3.051 3.05c.362.184.763.349 1.198.49zM3.509 7.5c.036-1.07.188-2.087.436-3.008a9.124 9.124 0 0 1-1.565-.667A6.964 6.964 0 0 0 1.018 7.5h2.49zm1.4-2.741a12.344 12.344 0 0 0-.4 2.741H7.5V5.091c-.91-.03-1.783-.145-2.591-.332zM8.5 5.09V7.5h2.99a12.342 12.342 0 0 0-.399-2.741c-.808.187-1.681.301-2.591.332zM4.51 8.5c.035.987.176 1.914.399 2.741A13.612 13.612 0 0 1 7.5 10.91V8.5H4.51zm3.99 0v2.409c.91.03 1.783.145 2.591.332.223-.827.364-1.754.4-2.741H8.5zm-3.282 3.696c.12.312.252.604.395.872.552 1.035 1.218 1.65 1.887 1.855V11.91c-.81.03-1.577.15-2.282.45zm.11 2.276a6.696 6.696 0 0 1-.598-.933 8.853 8.853 0 0 1-.481-1.079 8.38 8.38 0 0 0-1.198.49 7.01 7.01 0 0 0 2.276 1.522zm-1.383-2.964A13.36 13.36 0 0 1 3.508 8.5h-2.49a6.963 6.963 0 0 0 1.362 3.675c.47-.258.995-.482 1.565-.667zm6.728 2.964a7.009 7.009 0 0 0 2.275-1.521 8.376 8.376 0 0 0-1.197-.49 8.853 8.853 0 0 1-.481 1.078 6.688 6.688 0 0 1-.597.933zM8.5 11.909v3.014c.67-.204 1.335-.82 1.887-1.855.143-.268.276-.52.395-.872A12.63 12.63 0 0 0 8.5 11.91zm3.555-.401c.57.185 1.095.409 1.565.667A6.963 6.963 0 0 0 14.982 8.5h-2.49a13.36 13.36 0 0 1-.437 3.008zM14.982 7.5a6.963 6.963 0 0 0-1.362-3.675c-.47.258-.995.482-1.565.667.248.92.4 1.938.437 3.008h2.49zM11.27 2.461c.177.334.339.694.482 1.078a8.368 8.368 0 0 0 1.196-.49 7.01 7.01 0 0 0-2.275-1.52c.218.283.418.597.597.932zm-.488 1.343a7.765 7.765 0 0 0-.395-.872C9.835 1.897 9.17 1.282 8.5 1.077V4.09c.81-.03 1.577-.15 2.282-.45z"/>
                </svg>
              </button>
              
              <button
                className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white font-medium rounded-lg text-sm border border-zinc-700 disabled:opacity-50 transition-colors"
                onClick={showBrowser ? handleRunWithVisibleBrowser : handleRun}
                disabled={loading || !task.trim()}
              >
                {loading ? "Выполняется..." : "Выполнить"}
              </button>
              
              {loading && taskId && (
                <button
                  className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white font-medium rounded-lg text-sm border border-red-800 text-red-500 transition-colors"
                  onClick={handleCancel}
                >
                  Отменить
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
