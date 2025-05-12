import axios from 'axios';

/**
 * Базовый URL API сервера
 */
const BASE_URL = 'http://127.0.0.1:8000';

/**
 * Тип запроса на выполнение задачи
 */
interface RunRequest {
  task: string;
  headless: boolean;
  max_steps?: number;
  model?: string;
  provider?: string;
}

/**
 * Тип ответа на выполнение задачи
 */
interface RunResponse {
  result: string;
}

/**
 * Тип для создания задачи
 */
interface TaskRequest {
  task: string;
  headless: boolean;
  max_steps?: number;
  model?: string;
  provider?: string;
  use_vision?: boolean;
}

/**
 * Тип ответа при создании задачи
 */
interface TaskResponse {
  task_id: string;
  status: string;
  message: string;
}

/**
 * Тип результата задачи
 */
interface TaskResult {
  task_id: string;
  status: string;
  steps: number;
  results: {
    content?: string;
    error?: string;
    url?: string;
    title?: string;
  }[];
  error?: string;
}

/**
 * Класс сервиса для работы с браузерным агентом
 */
export class BrowserAgentService {
  /**
   * Выполняет задачу и ожидает результат
   * 
   * @param task Текст задачи
   * @param headless Режим без отображения браузера
   * @param options Дополнительные опции
   * @returns Результат выполнения задачи
   */
  static async runTask(
    task: string, 
    headless: boolean = true, 
    options: { model?: string; provider?: string; max_steps?: number } = {}
  ): Promise<string> {
    try {
      const response = await axios.post<RunResponse>(`${BASE_URL}/run`, {
        task,
        headless,
        model: options.model || 'gpt-4.1-nano-2025-04-14',
        provider: options.provider || 'openai',
        max_steps: options.max_steps || 5
      }, {
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        }
      });

      return response.data.result;
    } catch (error) {
      console.error('Ошибка при выполнении задачи:', error);
      throw new Error('Ошибка при выполнении задачи');
    }
  }

  /**
   * Создает новую задачу для выполнения в фоновом режиме
   * 
   * @param task Текст задачи
   * @param headless Режим без отображения браузера
   * @param options Дополнительные опции
   * @returns ID созданной задачи
   */
  static async createTask(
    task: string, 
    headless: boolean = false, 
    options: { model?: string; provider?: string; max_steps?: number; use_vision?: boolean } = {}
  ): Promise<string> {
    try {
      const response = await axios.post<TaskResponse>(`${BASE_URL}/task`, {
        task,
        headless,
        model: options.model || 'gpt-4.1-nano-2025-04-14',
        provider: options.provider || 'openai',
        max_steps: options.max_steps || 5,
        use_vision: options.use_vision !== false
      }, {
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        }
      });

      return response.data.task_id;
    } catch (error) {
      console.error('Ошибка при создании задачи:', error);
      throw new Error('Ошибка при создании задачи');
    }
  }

  /**
   * Получает статус и результаты задачи
   * 
   * @param taskId ID задачи
   * @returns Статус и результаты задачи
   */
  static async getTaskStatus(taskId: string): Promise<TaskResult> {
    try {
      const response = await axios.get<TaskResult>(`${BASE_URL}/task/${taskId}`);
      return response.data;
    } catch (error) {
      console.error('Ошибка при получении статуса задачи:', error);
      throw new Error('Ошибка при получении статуса задачи');
    }
  }

  /**
   * Отменяет выполнение задачи
   * 
   * @param taskId ID задачи
   * @returns Результат отмены
   */
  static async cancelTask(taskId: string): Promise<{ status: string; task_id: string }> {
    try {
      const response = await axios.delete(`${BASE_URL}/task/${taskId}`);
      return response.data;
    } catch (error) {
      console.error('Ошибка при отмене задачи:', error);
      throw new Error('Ошибка при отмене задачи');
    }
  }

  /**
   * Комбинирует результаты из шагов задачи в одну строку
   * 
   * @param results Массив результатов шагов задачи
   * @returns Комбинированный результат
   */
  static combineResults(results: TaskResult['results']): string {
    if (!results || results.length === 0) {
      return "Нет результатов";
    }
    
    return results
      .filter(step => step.content)
      .map(step => step.content)
      .join("\n\n");
  }
} 