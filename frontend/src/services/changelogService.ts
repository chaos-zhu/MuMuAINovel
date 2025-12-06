/**
 * GitHub 提交日志获取服务
 * 用于从 GitHub API 获取项目的提交历史并转换为更新日志
 */

export interface GitHubCommit {
  sha: string;
  commit: {
    author: {
      name: string;
      email: string;
      date: string;
    };
    message: string;
  };
  html_url: string;
  author: {
    login: string;
    avatar_url: string;
  } | null;
}

export interface ChangelogEntry {
  id: string;
  date: string;
  version?: string;
  author: {
    name: string;
    avatar?: string;
    username?: string;
  };
  message: string;
  commitUrl: string;
  type: 'feature' | 'fix' | 'docs' | 'style' | 'refactor' | 'perf' | 'test' | 'chore' | 'other';
  scope?: string;
}

const GITHUB_API_BASE = 'https://api.github.com';
const REPO_OWNER = 'xiamuceer-j';
const REPO_NAME = 'MuMuAINovel';

/**
 * 从提交信息中解析类型和作用域
 * 支持常见的提交信息格式：
 * - type: message
 * - type(scope): message
 * - [type] message
 */
function parseCommitType(message: string): { type: ChangelogEntry['type']; scope?: string; cleanMessage: string } {
  const lowerMessage = message.toLowerCase();
  
  // 第一优先级：精确匹配 update: 开头（在正则之前检查）
  if (lowerMessage.startsWith('update:')) {
    const cleanMsg = message.replace(/^update:\s*/i, '');
    return { type: 'feature', cleanMessage: cleanMsg };
  }
  
  // 第二优先级：匹配标准 conventional commits 格式 type: message 或 type(scope): message
  const conventionalMatch = message.match(/^(feat|feature|fix|docs|style|refactor|perf|test|chore)(?:\(([^)]+)\))?\s*:\s*(.+)/i);
  if (conventionalMatch) {
    const typeStr = conventionalMatch[1].toLowerCase();
    const mappedType = typeStr === 'feature' ? 'feature' : typeStr as ChangelogEntry['type'];
    return {
      type: mappedType,
      scope: conventionalMatch[2],
      cleanMessage: conventionalMatch[3],
    };
  }

  // 第三优先级：匹配 [type] message 格式
  const bracketMatch = message.match(/^\[(feat|feature|fix|docs|style|refactor|perf|test|chore|update)\]\s*(.+)/i);
  if (bracketMatch) {
    const typeStr = bracketMatch[1].toLowerCase();
    const mappedType = (typeStr === 'update' || typeStr === 'feature') ? 'feature' : typeStr as ChangelogEntry['type'];
    return {
      type: mappedType,
      cleanMessage: bracketMatch[2],
    };
  }

  // 第四优先级：通过前缀精确匹配（避免误判）
  if (lowerMessage.startsWith('fix:')|| lowerMessage.startsWith('fix：')) {
    const cleanMsg = message.replace(/^fix:\s*/i, '');
    return { type: 'fix', cleanMessage: cleanMsg };
  }
  
  if (lowerMessage.startsWith('perf:')) {
    const cleanMsg = message.replace(/^perf:\s*/i, '');
    return { type: 'perf', cleanMessage: cleanMsg };
  }
  
  if (lowerMessage.startsWith('docs:')) {
    const cleanMsg = message.replace(/^docs:\s*/i, '');
    return { type: 'docs', cleanMessage: cleanMsg };
  }
  
  if (lowerMessage.startsWith('feat:') || lowerMessage.startsWith('feature:')) {
    const cleanMsg = message.replace(/^(feat|feature):\s*/i, '');
    return { type: 'feature', cleanMessage: cleanMsg };
  }
  
  // 第五优先级：关键词模糊匹配（仅当前面都不匹配时）
  if (lowerMessage.includes('修复') || lowerMessage.includes('fix')) {
    return { type: 'fix', cleanMessage: message };
  }
  
  if (lowerMessage.includes('优化') || lowerMessage.includes('perf')) {
    return { type: 'perf', cleanMessage: message };
  }
  
  if (lowerMessage.includes('文档') || lowerMessage.includes('doc')) {
    return { type: 'docs', cleanMessage: message };
  }
  
  if (lowerMessage.includes('新增') || lowerMessage.includes('添加') || lowerMessage.includes('增加')) {
    return { type: 'feature', cleanMessage: message };
  }
  
  if (lowerMessage.includes('样式') || lowerMessage.includes('style')) {
    return { type: 'style', cleanMessage: message };
  }
  
  if (lowerMessage.includes('重构') || lowerMessage.includes('refactor')) {
    return { type: 'refactor', cleanMessage: message };
  }

  return { type: 'other', cleanMessage: message };
}

/**
 * 获取GitHub提交历史
 */
export async function fetchGitHubCommits(page: number = 1, perPage: number = 30): Promise<GitHubCommit[]> {
  try {
    const url = `${GITHUB_API_BASE}/repos/${REPO_OWNER}/${REPO_NAME}/commits?author=${REPO_OWNER}&page=${page}&per_page=${perPage}`;
    
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Accept': 'application/vnd.github.v3+json',
      },
      cache: 'no-cache',
    });

    if (!response.ok) {
      throw new Error(`GitHub API 请求失败: ${response.status} ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    console.error('获取 GitHub 提交历史失败:', error);
    throw error;
  }
}

/**
 * 将GitHub提交转换为更新日志条目
 */
export function convertCommitsToChangelog(commits: GitHubCommit[]): ChangelogEntry[] {
  return commits.map(commit => {
    const { type, scope, cleanMessage } = parseCommitType(commit.commit.message);
    
    return {
      id: commit.sha,
      date: commit.commit.author.date,
      author: {
        name: commit.commit.author.name,
        avatar: commit.author?.avatar_url,
        username: commit.author?.login,
      },
      message: cleanMessage,
      commitUrl: commit.html_url,
      type,
      scope,
    };
  });
}

/**
 * 获取格式化的更新日志
 */
export async function fetchChangelog(page: number = 1, perPage: number = 30): Promise<ChangelogEntry[]> {
  const commits = await fetchGitHubCommits(page, perPage);
  return convertCommitsToChangelog(commits);
}

/**
 * 按日期分组更新日志
 */
export function groupChangelogByDate(entries: ChangelogEntry[]): Map<string, ChangelogEntry[]> {
  const grouped = new Map<string, ChangelogEntry[]>();
  
  entries.forEach(entry => {
    const date = new Date(entry.date).toISOString().split('T')[0];
    const existing = grouped.get(date) || [];
    existing.push(entry);
    grouped.set(date, existing);
  });
  
  return grouped;
}

/**
 * 检查是否应该获取更新日志（避免频繁请求）
 */
export function shouldFetchChangelog(): boolean {
  const lastFetch = localStorage.getItem('changelog_last_fetch');
  
  if (!lastFetch) {
    return true;
  }
  
  const lastFetchTime = new Date(lastFetch).getTime();
  const now = Date.now();
  const oneHourMs = 60 * 60 * 1000; // 1小时
  
  return now - lastFetchTime >= oneHourMs;
}

/**
 * 记录更新日志获取时间
 */
export function markChangelogFetched(): void {
  localStorage.setItem('changelog_last_fetch', new Date().toISOString());
}

/**
 * 获取缓存的更新日志
 */
export function getCachedChangelog(): ChangelogEntry[] | null {
  const cached = localStorage.getItem('changelog_cache');
  if (cached) {
    try {
      return JSON.parse(cached);
    } catch {
      return null;
    }
  }
  return null;
}

/**
 * 缓存更新日志
 */
export function cacheChangelog(entries: ChangelogEntry[]): void {
  localStorage.setItem('changelog_cache', JSON.stringify(entries));
}

/**
 * 清除更新日志缓存
 * 用于强制刷新数据
 */
export function clearChangelogCache(): void {
  localStorage.removeItem('changelog_cache');
  localStorage.removeItem('changelog_last_fetch');
}