import axios from 'axios';
import { message } from 'antd';
import { ssePost } from '../utils/sseClient';
import type { SSEClientOptions } from '../utils/sseClient';
import type {
  User,
  AuthUrlResponse,
  Project,
  ProjectCreate,
  ProjectUpdate,
  WorldBuildingResponse,
  Outline,
  OutlineCreate,
  OutlineUpdate,
  OutlineReorderRequest,
  Character,
  CharacterUpdate,
  Chapter,
  ChapterCreate,
  ChapterUpdate,
  GenerateOutlineRequest,
  GenerateCharacterRequest,
  PolishTextRequest,
  GenerateCharactersResponse,
  GenerateOutlineResponse,
  Settings,
  SettingsUpdate,
  WritingStyle,
  WritingStyleCreate,
  WritingStyleUpdate,
  PresetStyle,
  WritingStyleListResponse,
} from '../types';

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

api.interceptors.request.use(
  (config) => {
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

api.interceptors.response.use(
  (response) => {
    return response.data;
  },
  (error) => {
    let errorMessage = '请求失败';
    
    if (error.response) {
      const status = error.response.status;
      const data = error.response.data;
      
      switch (status) {
        case 400:
          errorMessage = data?.detail || '请求参数错误';
          break;
        case 401:
          errorMessage = '未授权，请先登录';
          if (window.location.pathname !== '/login') {
            window.location.href = '/login';
          }
          break;
        case 403:
          errorMessage = '没有权限访问';
          break;
        case 404:
          errorMessage = data?.detail || '请求的资源不存在';
          break;
        case 422:
          errorMessage = data?.detail || '请求参数验证失败';
          if (data?.errors) {
            console.error('验证错误详情:', data.errors);
          }
          break;
        case 500:
          errorMessage = data?.detail || '服务器内部错误';
          break;
        case 503:
          errorMessage = '服务暂时不可用，请稍后重试';
          break;
        default:
          errorMessage = data?.detail || data?.message || `请求失败 (${status})`;
      }
    } else if (error.request) {
      errorMessage = '网络错误，请检查网络连接';
    } else {
      errorMessage = error.message || '请求失败';
    }
    
    message.error(errorMessage);
    console.error('API Error:', errorMessage, error);
    
    return Promise.reject(error);
  }
);

export const authApi = {
  getAuthConfig: () => api.get<unknown, { local_auth_enabled: boolean; linuxdo_enabled: boolean }>('/auth/config'),
  
  localLogin: (username: string, password: string) =>
    api.post<unknown, { success: boolean; message: string; user: User }>('/auth/local/login', { username, password }),
  
  getLinuxDOAuthUrl: () => api.get<unknown, AuthUrlResponse>('/auth/linuxdo/url'),
  
  getCurrentUser: () => api.get<unknown, User>('/auth/user'),
  
  logout: () => api.post('/auth/logout'),
};

export const userApi = {
  getCurrentUser: () => api.get<unknown, User>('/users/current'),
  
  listUsers: () => api.get<unknown, User[]>('/users'),
  
  setAdmin: (userId: string, isAdmin: boolean) =>
    api.post('/users/set-admin', { user_id: userId, is_admin: isAdmin }),
  
  deleteUser: (userId: string) => api.delete(`/users/${userId}`),
  
  getUser: (userId: string) => api.get<unknown, User>(`/users/${userId}`),
};

export const settingsApi = {
  getSettings: () => api.get<unknown, Settings>('/settings'),
  
  saveSettings: (data: SettingsUpdate) =>
    api.post<unknown, Settings>('/settings', data),
  
  updateSettings: (data: SettingsUpdate) =>
    api.put<unknown, Settings>('/settings', data),
  
  deleteSettings: () => api.delete<unknown, { message: string; user_id: string }>('/settings'),
  
  getAvailableModels: (params: { api_key: string; api_base_url: string; provider: string }) =>
    api.get<unknown, { provider: string; models: Array<{ value: string; label: string; description: string }>; count?: number }>('/settings/models', { params }),
};

export const projectApi = {
  getProjects: () => api.get<unknown, Project[]>('/projects'),
  
  getProject: (id: string) => api.get<unknown, Project>(`/projects/${id}`),
  
  createProject: (data: ProjectCreate) => api.post<unknown, Project>('/projects', data),
  
  updateProject: (id: string, data: ProjectUpdate) =>
    api.put<unknown, Project>(`/projects/${id}`, data),
  
  deleteProject: (id: string) => api.delete(`/projects/${id}`),
  
  exportProject: (id: string) => {
    window.open(`/api/projects/${id}/export`, '_blank');
  },
};

export const outlineApi = {
  getOutlines: (projectId: string) =>
    api.get<unknown, { total: number; items: Outline[] }>(`/outlines/project/${projectId}`).then(res => res.items),
  
  getOutline: (id: string) => api.get<unknown, Outline>(`/outlines/${id}`),
  
  createOutline: (data: OutlineCreate) => api.post<unknown, Outline>('/outlines', data),
  
  updateOutline: (id: string, data: OutlineUpdate) =>
    api.put<unknown, Outline>(`/outlines/${id}`, data),
  
  deleteOutline: (id: string) => api.delete(`/outlines/${id}`),
  
  reorderOutlines: (data: OutlineReorderRequest) =>
    api.post<unknown, { message: string; updated_outlines: number; updated_chapters: number }>('/outlines/reorder', data),
  
  generateOutline: (data: GenerateOutlineRequest) =>
    api.post<unknown, { total: number; items: Outline[] }>('/outlines/generate', data).then(res => res.items),
};

export const characterApi = {
  getCharacters: (projectId: string) =>
    api.get<unknown, Character[]>(`/characters/project/${projectId}`),
  
  getCharacter: (id: string) => api.get<unknown, Character>(`/characters/${id}`),
  
  updateCharacter: (id: string, data: CharacterUpdate) =>
    api.put<unknown, Character>(`/characters/${id}`, data),
  
  deleteCharacter: (id: string) => api.delete(`/characters/${id}`),
  
  generateCharacter: (data: GenerateCharacterRequest) =>
    api.post<unknown, Character>('/characters/generate', data),
};

export const chapterApi = {
  getChapters: (projectId: string) =>
    api.get<unknown, Chapter[]>(`/chapters/project/${projectId}`),
  
  getChapter: (id: string) => api.get<unknown, Chapter>(`/chapters/${id}`),
  
  createChapter: (data: ChapterCreate) => api.post<unknown, Chapter>('/chapters', data),
  
  updateChapter: (id: string, data: ChapterUpdate) =>
    api.put<unknown, Chapter>(`/chapters/${id}`, data),
  
  deleteChapter: (id: string) => api.delete(`/chapters/${id}`),
  
  checkCanGenerate: (chapterId: string) =>
    api.get<unknown, import('../types').ChapterCanGenerateResponse>(`/chapters/${chapterId}/can-generate`),
};

export const writingStyleApi = {
  // 获取预设风格列表
  getPresetStyles: () =>
    api.get<unknown, PresetStyle[]>('/writing-styles/presets/list'),
  
  // 获取项目的所有风格
  getProjectStyles: (projectId: string) =>
    api.get<unknown, WritingStyleListResponse>(`/writing-styles/project/${projectId}`),
  
  // 创建新风格（基于预设或自定义）
  createStyle: (data: WritingStyleCreate) =>
    api.post<unknown, WritingStyle>('/writing-styles', data),
  
  // 更新风格
  updateStyle: (styleId: number, data: WritingStyleUpdate) =>
    api.put<unknown, WritingStyle>(`/writing-styles/${styleId}`, data),
  
  // 删除风格
  deleteStyle: (styleId: number) =>
    api.delete<unknown, { message: string }>(`/writing-styles/${styleId}`),
  
  // 设置默认风格
  setDefaultStyle: (styleId: number, projectId: string) =>
    api.post<unknown, WritingStyle>(`/writing-styles/${styleId}/set-default`, { project_id: projectId }),
  
  // 为项目初始化默认风格（如果没有任何风格）
  initializeDefaultStyles: (projectId: string) =>
    api.post<unknown, WritingStyleListResponse>(`/writing-styles/project/${projectId}/initialize`, {}),
};

export const polishApi = {
  polishText: (data: PolishTextRequest) =>
    api.post<unknown, { polished_text: string }>('/polish', data),
  
  polishBatch: (texts: string[]) =>
    api.post<unknown, { polished_texts: string[] }>('/polish/batch', { texts }),
};
export default api;


export const wizardStreamApi = {
  generateWorldBuildingStream: (
    data: {
      title: string;
      description: string;
      theme: string;
      genre: string | string[];
      narrative_perspective?: string;
      target_words?: number;
      chapter_count?: number;
      character_count?: number;
      provider?: string;
      model?: string;
    },
    options?: SSEClientOptions
  ) => ssePost<WorldBuildingResponse>(
    '/api/wizard-stream/world-building',
    data,
    options
  ),

  generateCharactersStream: (
    data: {
      project_id: string;
      count?: number;
      world_context?: Record<string, string>;
      theme?: string;
      genre?: string;
      requirements?: string;
      provider?: string;
      model?: string;
    },
    options?: SSEClientOptions
  ) => ssePost<GenerateCharactersResponse>(
    '/api/wizard-stream/characters',
    data,
    options
  ),

  generateCompleteOutlineStream: (
    data: {
      project_id: string;
      chapter_count: number;
      narrative_perspective: string;
      target_words?: number;
      requirements?: string;
      provider?: string;
      model?: string;
    },
    options?: SSEClientOptions
  ) => ssePost<GenerateOutlineResponse>(
    '/api/wizard-stream/outline',
    data,
    options
  ),

  updateWorldBuildingStream: (
    projectId: string,
    data: {
      time_period?: string;
      location?: string;
      atmosphere?: string;
      rules?: string;
    },
    options?: SSEClientOptions
  ) => ssePost<WorldBuildingResponse>(
    `/api/wizard-stream/world-building/${projectId}`,
    data,
    options
  ),

  regenerateWorldBuildingStream: (
    projectId: string,
    data?: {
      provider?: string;
      model?: string;
    },
    options?: SSEClientOptions
  ) => ssePost<WorldBuildingResponse>(
    `/api/wizard-stream/world-building/${projectId}/regenerate`,
    data || {},
    options
  ),

  cleanupWizardDataStream: (
    projectId: string,
    options?: SSEClientOptions
  ) => ssePost<{ message: string; deleted: { characters: number; outlines: number; chapters: number } }>(
    `/api/wizard-stream/cleanup/${projectId}`,
    {},
    options
  ),
};