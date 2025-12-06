import { Modal, Timeline, Tag, Avatar, Empty, Spin, Button, Space, Tooltip } from 'antd';
import { useState, useEffect } from 'react';
import {
  BugOutlined,
  StarOutlined,
  FileTextOutlined,
  BgColorsOutlined,
  ThunderboltOutlined,
  ExperimentOutlined,
  ToolOutlined,
  QuestionCircleOutlined,
  GithubOutlined,
  ReloadOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import {
  fetchChangelog,
  groupChangelogByDate,
  getCachedChangelog,
  cacheChangelog,
  markChangelogFetched,
  shouldFetchChangelog,
  clearChangelogCache,
  type ChangelogEntry,
} from '../services/changelogService';

interface ChangelogModalProps {
  visible: boolean;
  onClose: () => void;
}

// 提交类型图标和颜色配置
const typeConfig: Record<ChangelogEntry['type'], { icon: React.ReactNode; color: string; label: string }> = {
  feature: { icon: <StarOutlined />, color: 'green', label: '新功能' },
  fix: { icon: <BugOutlined />, color: 'red', label: '修复' },
  docs: { icon: <FileTextOutlined />, color: 'blue', label: '文档' },
  style: { icon: <BgColorsOutlined />, color: 'purple', label: '样式' },
  refactor: { icon: <ThunderboltOutlined />, color: 'orange', label: '重构' },
  perf: { icon: <ThunderboltOutlined />, color: 'gold', label: '性能' },
  test: { icon: <ExperimentOutlined />, color: 'cyan', label: '测试' },
  chore: { icon: <ToolOutlined />, color: 'default', label: '杂项' },
  other: { icon: <QuestionCircleOutlined />, color: 'default', label: '其他' },
};

export default function ChangelogModal({ visible, onClose }: ChangelogModalProps) {
  const [changelog, setChangelog] = useState<ChangelogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  // 加载更新日志
  const loadChangelog = async (pageNum: number = 1, append: boolean = false) => {
    setLoading(true);
    setError(null);

    try {
      // 如果是第一页，先尝试使用缓存
      if (pageNum === 1 && !append) {
        const cached = getCachedChangelog();
        if (cached && cached.length > 0) {
          setChangelog(cached);
          
          // 后台刷新
          if (shouldFetchChangelog()) {
            fetchChangelog(pageNum, 30)
              .then(entries => {
                setChangelog(entries);
                cacheChangelog(entries);
                markChangelogFetched();
              })
              .catch(console.error);
          }
          
          setLoading(false);
          return;
        }
      }

      const entries = await fetchChangelog(pageNum, 30);
      
      if (entries.length === 0) {
        setHasMore(false);
      } else {
        if (append) {
          setChangelog(prev => [...prev, ...entries]);
        } else {
          setChangelog(entries);
          // 缓存第一页数据
          if (pageNum === 1) {
            cacheChangelog(entries);
            markChangelogFetched();
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取更新日志失败');
    } finally {
      setLoading(false);
    }
  };

  // 初始加载
  useEffect(() => {
    if (visible) {
      loadChangelog(1, false);
      setPage(1);
      setHasMore(true);
    }
  }, [visible]);

  // 加载更多
  const handleLoadMore = () => {
    const nextPage = page + 1;
    setPage(nextPage);
    loadChangelog(nextPage, true);
  };

  // 刷新（清除缓存并重新加载）
  const handleRefresh = () => {
    clearChangelogCache();
    setPage(1);
    setHasMore(true);
    loadChangelog(1, false);
  };

  // 按日期分组
  const groupedChangelog = groupChangelogByDate(changelog);
  const sortedDates = Array.from(groupedChangelog.keys()).sort((a, b) => b.localeCompare(a));

  // 格式化日期
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return '今天';
    if (diffDays === 1) return '昨天';
    if (diffDays < 7) return `${diffDays} 天前`;
    
    return date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' });
  };

  // 格式化时间
  const formatTime = (dateStr: string) => {
    return new Date(dateStr).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <Modal
      title={
        <Space>
          <GithubOutlined />
          <span>更新日志</span>
          <Tooltip title="刷新">
            <Button
              type="text"
              size="small"
              icon={<ReloadOutlined />}
              onClick={handleRefresh}
              loading={loading}
            />
          </Tooltip>
        </Space>
      }
      open={visible}
      onCancel={onClose}
      footer={null}
      width={800}
      centered
      styles={{
        body: {
          maxHeight: '70vh',
          overflowY: 'auto',
          padding: '24px',
        },
      }}
    >
      {error && (
        <div style={{
          padding: '16px',
          marginBottom: '16px',
          background: '#fff2e8',
          border: '1px solid #ffbb96',
          borderRadius: '4px',
          color: '#d4380d',
        }}>
          {error}
        </div>
      )}

      {loading && changelog.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin size="large" tip="加载更新日志中..." />
        </div>
      ) : changelog.length === 0 ? (
        <Empty description="暂无更新日志" />
      ) : (
        <>
          {sortedDates.map(date => {
            const entries = groupedChangelog.get(date) || [];
            
            return (
              <div key={date} style={{ marginBottom: '32px' }}>
                <div style={{
                  fontSize: '16px',
                  fontWeight: 600,
                  color: '#1890ff',
                  marginBottom: '16px',
                  paddingBottom: '8px',
                  borderBottom: '2px solid #e8e8e8',
                }}>
                  <ClockCircleOutlined style={{ marginRight: '8px' }} />
                  {formatDate(date)}
                </div>

                <Timeline>
                  {entries.map(entry => {
                    const config = typeConfig[entry.type] || typeConfig.other;
                    
                    return (
                      <Timeline.Item
                        key={entry.id}
                        dot={
                          <div style={{
                            width: '24px',
                            height: '24px',
                            borderRadius: '50%',
                            background: '#fff',
                            border: `2px solid ${config.color === 'default' ? '#d9d9d9' : config.color}`,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '12px',
                          }}>
                            {config.icon}
                          </div>
                        }
                      >
                        <div style={{ marginLeft: '8px' }}>
                          <Space size="small" wrap>
                            <Tag color={config.color} icon={config.icon}>
                              {config.label}
                            </Tag>
                            {entry.scope && (
                              <Tag color="blue">{entry.scope}</Tag>
                            )}
                            <span style={{ color: '#999', fontSize: '12px' }}>
                              {formatTime(entry.date)}
                            </span>
                          </Space>

                          <div style={{
                            marginTop: '8px',
                            fontSize: '14px',
                            lineHeight: '1.6',
                            color: '#333',
                          }}>
                            {entry.message}
                          </div>

                          <Space size="small" style={{ marginTop: '8px' }}>
                            {entry.author.avatar && (
                              <Avatar size="small" src={entry.author.avatar} />
                            )}
                            <span style={{ color: '#666', fontSize: '13px' }}>
                              {entry.author.username || entry.author.name}
                            </span>
                            <a
                              href={entry.commitUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{ fontSize: '12px' }}
                            >
                              查看提交
                            </a>
                          </Space>
                        </div>
                      </Timeline.Item>
                    );
                  })}
                </Timeline>
              </div>
            );
          })}

          {hasMore && (
            <div style={{ textAlign: 'center', marginTop: '24px' }}>
              <Button
                type="default"
                onClick={handleLoadMore}
                loading={loading}
              >
                加载更多
              </Button>
            </div>
          )}

          {!hasMore && changelog.length > 0 && (
            <div style={{
              textAlign: 'center',
              color: '#999',
              padding: '16px 0',
              fontSize: '14px',
            }}>
              已显示所有更新日志
            </div>
          )}
        </>
      )}

      <div style={{
        marginTop: '24px',
        padding: '12px',
        background: '#f0f5ff',
        borderRadius: '4px',
        border: '1px solid #adc6ff',
        fontSize: '13px',
        color: '#1d39c4',
      }}>
        💡 提示：更新日志每小时自动刷新一次，数据来源于 GitHub 提交历史
      </div>
    </Modal>
  );
}