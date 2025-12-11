import { useState, useEffect } from 'react';
import { Button, List, Modal, Form, Input, message, Empty, Space, Popconfirm, Card, Select, Radio, Tag, InputNumber, Tooltip, Tabs } from 'antd';
import { EditOutlined, DeleteOutlined, ThunderboltOutlined, BranchesOutlined, AppstoreAddOutlined, CheckCircleOutlined, ExclamationCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { useStore } from '../store';
import { useOutlineSync } from '../store/hooks';
import { cardStyles } from '../components/CardStyles';
import { SSEPostClient } from '../utils/sseClient';
import { SSEProgressModal } from '../components/SSEProgressModal';
import { outlineApi, chapterApi, projectApi } from '../services/api';
import type { OutlineExpansionResponse, BatchOutlineExpansionResponse } from '../types';

// 角色预测数据类型
interface PredictedCharacter {
  name?: string;
  role_description: string;
  suggested_role_type: string;
  importance: string;
  appearance_chapter: number;
  key_abilities: string[];
  plot_function: string;
  relationship_suggestions: Array<{
    target_character_name: string;
    relationship_type: string;
    description?: string;
  }>;
}

interface CharacterConfirmationData {
  code: string;
  message: string;
  predicted_characters: PredictedCharacter[];
  reason: string;
  chapter_range: string;
}

const { TextArea } = Input;

export default function Outline() {
  const { currentProject, outlines, setCurrentProject } = useStore();
  const [isGenerating, setIsGenerating] = useState(false);
  const [editForm] = Form.useForm();
  const [generateForm] = Form.useForm();
  const [expansionForm] = Form.useForm();
  const [batchExpansionForm] = Form.useForm();
  const [manualCreateForm] = Form.useForm();
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);
  const [isExpanding, setIsExpanding] = useState(false);

  // ✅ 新增：记录每个大纲的展开状态
  const [outlineExpandStatus, setOutlineExpandStatus] = useState<Record<string, boolean>>({});

  // 角色确认相关状态
  const [characterConfirmData, setCharacterConfirmData] = useState<CharacterConfirmationData | null>(null);
  const [characterConfirmVisible, setCharacterConfirmVisible] = useState(false);
  const [pendingGenerateData, setPendingGenerateData] = useState<any>(null);
  const [selectedCharacterIndices, setSelectedCharacterIndices] = useState<number[]>([]);

  // 缓存批量展开的规划数据，避免重复AI调用
  const [cachedBatchExpansionResponse, setCachedBatchExpansionResponse] = useState<BatchOutlineExpansionResponse | null>(null);

  // 批量展开预览的状态
  const [batchPreviewVisible, setBatchPreviewVisible] = useState(false);
  const [batchPreviewData, setBatchPreviewData] = useState<BatchOutlineExpansionResponse | null>(null);
  const [selectedOutlineIdx, setSelectedOutlineIdx] = useState(0);
  const [selectedChapterIdx, setSelectedChapterIdx] = useState(0);

  // SSE进度状态
  const [sseProgress, setSSEProgress] = useState(0);
  const [sseMessage, setSSEMessage] = useState('');
  const [sseModalVisible, setSSEModalVisible] = useState(false);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth <= 768);
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // 使用同步 hooks
  const {
    refreshOutlines,
    updateOutline,
    deleteOutline
  } = useOutlineSync();

  // 初始加载大纲列表
  useEffect(() => {
    if (currentProject?.id) {
      refreshOutlines();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentProject?.id]); // 只依赖 ID，不依赖函数

  // ✅ 新增：加载所有大纲的展开状态
  useEffect(() => {
    const loadExpandStatus = async () => {
      if (outlines.length === 0) return;

      const statusMap: Record<string, boolean> = {};
      for (const outline of outlines) {
        try {
          const chapters = await outlineApi.getOutlineChapters(outline.id);
          statusMap[outline.id] = chapters.has_chapters;
        } catch (error) {
          console.error(`加载大纲 ${outline.id} 状态失败:`, error);
          statusMap[outline.id] = false;
        }
      }
      setOutlineExpandStatus(statusMap);
    };

    loadExpandStatus();
  }, [outlines]);

  // 当角色确认数据变化时，初始化选中状态（默认全选）
  useEffect(() => {
    if (characterConfirmData) {
      setSelectedCharacterIndices(
        characterConfirmData.predicted_characters.map((_, idx) => idx)
      );
    }
  }, [characterConfirmData]);

  // 移除事件监听，避免无限循环
  // Hook 内部已经更新了 store，不需要再次刷新

  if (!currentProject) return null;

  // 确保大纲按 order_index 排序
  const sortedOutlines = [...outlines].sort((a, b) => a.order_index - b.order_index);

  const handleOpenEditModal = (id: string) => {
    const outline = outlines.find(o => o.id === id);
    if (outline) {
      editForm.setFieldsValue(outline);
      Modal.confirm({
        title: '编辑大纲',
        width: 600,
        centered: true,
        content: (
          <Form
            form={editForm}
            layout="vertical"
            style={{ marginTop: 16 }}
          >
            <Form.Item
              label="标题"
              name="title"
              rules={[{ required: true, message: '请输入标题' }]}
            >
              <Input placeholder="输入大纲标题" />
            </Form.Item>

            <Form.Item
              label="内容"
              name="content"
              rules={[{ required: true, message: '请输入内容' }]}
            >
              <TextArea rows={6} placeholder="输入大纲内容..." />
            </Form.Item>
          </Form>
        ),
        okText: '更新',
        cancelText: '取消',
        onOk: async () => {
          const values = await editForm.validateFields();
          try {
            await updateOutline(id, values);
            message.success('大纲更新成功');
          } catch {
            message.error('更新失败');
          }
        },
      });
    }
  };

  const handleDeleteOutline = async (id: string) => {
    try {
      await deleteOutline(id);
      message.success('删除成功');
      // 删除后刷新大纲列表和项目信息，更新字数显示
      await refreshOutlines();
      if (currentProject?.id) {
        const updatedProject = await projectApi.getProject(currentProject.id);
        setCurrentProject(updatedProject);
      }
    } catch {
      message.error('删除失败');
    }
  };

  interface GenerateFormValues {
    theme?: string;
    chapter_count?: number;
    narrative_perspective?: string;
    requirements?: string;
    provider?: string;
    model?: string;
    mode?: 'auto' | 'new' | 'continue';
    story_direction?: string;
    plot_stage?: 'development' | 'climax' | 'ending';
    keep_existing?: boolean;
    enable_auto_characters?: boolean;
  }

  const handleGenerate = async (values: GenerateFormValues) => {
    try {
      setIsGenerating(true);

      // 添加详细的调试日志
      console.log('=== 大纲生成调试信息 ===');
      console.log('1. Form values 原始数据:', values);
      console.log('2. values.model:', values.model);
      console.log('3. values.provider:', values.provider);

      // 关闭生成表单Modal
      Modal.destroyAll();

      // 显示进度Modal
      setSSEProgress(0);
      setSSEMessage('正在连接AI服务...');
      setSSEModalVisible(true);

      // 准备请求数据
      const requestData: any = {
        project_id: currentProject.id,
        genre: currentProject.genre || '通用',
        theme: values.theme || currentProject.theme || '',
        chapter_count: values.chapter_count || 5,
        narrative_perspective: values.narrative_perspective || currentProject.narrative_perspective || '第三人称',
        target_words: currentProject.target_words || 100000,
        requirements: values.requirements,
        mode: values.mode || 'auto',
        story_direction: values.story_direction,
        plot_stage: values.plot_stage || 'development',
        enable_auto_characters: values.enable_auto_characters !== undefined ? values.enable_auto_characters : true
      };

      // 只有在用户选择了模型时才添加model参数
      if (values.model) {
        requestData.model = values.model;
        console.log('4. 添加model到请求:', values.model);
      } else {
        console.log('4. values.model为空，不添加到请求');
      }

      // 添加provider参数（如果有）
      if (values.provider) {
        requestData.provider = values.provider;
        console.log('5. 添加provider到请求:', values.provider);
      }

      console.log('6. 最终请求数据:', JSON.stringify(requestData, null, 2));
      console.log('=========================');

      // 使用SSE客户端
      const apiUrl = `/api/outlines/generate-stream`;
      const client = new SSEPostClient(apiUrl, requestData, {
        onProgress: (msg: string, progress: number) => {
          setSSEMessage(msg);
          setSSEProgress(progress);
        },
        onResult: (data: any) => {
          console.log('生成完成，结果:', data);
        },
        onCharacterConfirmation: (data: any) => {
          // ✨ 新增：处理角色确认事件
          console.log('收到角色确认请求:', data);
          // 关闭SSE进度Modal
          setSSEModalVisible(false);
          setIsGenerating(false);

          // 保存待处理的生成数据
          setPendingGenerateData(requestData);

          // 显示角色确认对话框
          setCharacterConfirmData(data);
          setCharacterConfirmVisible(true);
        },
        onError: (error: string) => {
          // 现在只处理真正的错误
          message.error(`生成失败: ${error}`);
          setSSEModalVisible(false);
          setIsGenerating(false);
        },
        onComplete: () => {
          message.success('大纲生成完成！');
          setSSEModalVisible(false);
          setIsGenerating(false);
          // 刷新大纲列表
          refreshOutlines();
        }
      });

      // 开始连接
      client.connect();

    } catch (error) {
      console.error('AI生成失败:', error);
      message.error('AI生成失败');
      setSSEModalVisible(false);
      setIsGenerating(false);
    }
  };

  const showGenerateModal = async () => {
    const hasOutlines = outlines.length > 0;
    const initialMode = hasOutlines ? 'continue' : 'new';

    // 直接加载可用模型列表
    const settingsResponse = await fetch('/api/settings');
    const settings = await settingsResponse.json();
    const { api_key, api_base_url, api_provider } = settings;

    let loadedModels: Array<{ value: string, label: string }> = [];
    let defaultModel: string | undefined = undefined;

    if (api_key && api_base_url) {
      try {
        const modelsResponse = await fetch(
          `/api/settings/models?api_key=${encodeURIComponent(api_key)}&api_base_url=${encodeURIComponent(api_base_url)}&provider=${api_provider}`
        );
        if (modelsResponse.ok) {
          const data = await modelsResponse.json();
          if (data.models && data.models.length > 0) {
            loadedModels = data.models;
            defaultModel = settings.llm_model;
          }
        }
      } catch (error) {
        console.log('获取模型列表失败，将使用默认模型');
      }
    }

    Modal.confirm({
      title: hasOutlines ? (
        <Space>
          <span>AI生成/续写大纲</span>
          <Tag color="blue">当前已有 {outlines.length} 卷</Tag>
        </Space>
      ) : 'AI生成大纲',
      width: 700,
      centered: true,
      content: (
        <Form
          form={generateForm}
          layout="vertical"
          style={{ marginTop: 16 }}
          initialValues={{
            mode: initialMode,
            chapter_count: 5,
            narrative_perspective: currentProject.narrative_perspective || '第三人称',
            plot_stage: 'development',
            keep_existing: true,
            theme: currentProject.theme || '',
            model: defaultModel, // 添加默认模型
            enable_auto_characters: false, // 默认禁用自动角色引入
          }}
        >
          {hasOutlines && (
            <Form.Item
              label="生成模式"
              name="mode"
              tooltip="自动判断：根据是否有大纲自动选择；全新生成：删除旧大纲重新生成；续写模式：基于已有大纲继续创作"
            >
              <Radio.Group buttonStyle="solid">
                <Radio.Button value="auto">自动判断</Radio.Button>
                <Radio.Button value="new">全新生成</Radio.Button>
                <Radio.Button value="continue">续写模式</Radio.Button>
              </Radio.Group>
            </Form.Item>
          )}

          <Form.Item
            noStyle
            shouldUpdate={(prevValues, currentValues) => prevValues.mode !== currentValues.mode}
          >
            {({ getFieldValue }) => {
              const mode = getFieldValue('mode');
              const isContinue = mode === 'continue' || (mode === 'auto' && hasOutlines);

              // 续写模式不显示主题输入，使用项目原有主题
              if (isContinue) {
                return null;
              }

              // 全新生成模式需要输入主题
              return (
                <Form.Item
                  label="故事主题"
                  name="theme"
                  rules={[{ required: true, message: '请输入故事主题' }]}
                >
                  <TextArea rows={3} placeholder="描述你的故事主题、核心设定和主要情节..." />
                </Form.Item>
              );
            }}
          </Form.Item>

          <Form.Item
            noStyle
            shouldUpdate={(prevValues, currentValues) => prevValues.mode !== currentValues.mode}
          >
            {({ getFieldValue }) => {
              const mode = getFieldValue('mode');
              const isContinue = mode === 'continue' || (mode === 'auto' && hasOutlines);

              return (
                <>
                  {isContinue && (
                    <>
                      <Form.Item
                        label="故事发展方向"
                        name="story_direction"
                        tooltip="告诉AI你希望故事接下来如何发展"
                      >
                        <TextArea
                          rows={3}
                          placeholder="例如：主角遇到新的挑战、引入新角色、揭示关键秘密等..."
                        />
                      </Form.Item>

                      <Form.Item
                        label="情节阶段"
                        name="plot_stage"
                        tooltip="帮助AI理解当前故事所处的阶段"
                      >
                        <Select>
                          <Select.Option value="development">发展阶段 - 继续展开情节</Select.Option>
                          <Select.Option value="climax">高潮阶段 - 矛盾激化</Select.Option>
                          <Select.Option value="ending">结局阶段 - 收束伏笔</Select.Option>
                        </Select>
                      </Form.Item>
                    </>
                  )}

                  <Form.Item
                    label={isContinue ? "续写章节数" : "章节数量"}
                    name="chapter_count"
                    rules={[{ required: true, message: '请输入章节数量' }]}
                  >
                    <Input
                      type="number"
                      min={1}
                      max={50}
                      placeholder={isContinue ? "建议5-10章" : "如：30"}
                    />
                  </Form.Item>

                  <Form.Item
                    label="叙事视角"
                    name="narrative_perspective"
                    rules={[{ required: true, message: '请选择叙事视角' }]}
                  >
                    <Select>
                      <Select.Option value="第一人称">第一人称</Select.Option>
                      <Select.Option value="第三人称">第三人称</Select.Option>
                      <Select.Option value="全知视角">全知视角</Select.Option>
                    </Select>
                  </Form.Item>

                  <Form.Item label="其他要求" name="requirements">
                    <TextArea rows={2} placeholder="其他特殊要求（可选）" />
                  </Form.Item>

                  {/* 自动角色引入开关 - 仅在续写模式显示 */}
                  {isContinue && (
                    <Form.Item
                      label="智能角色引入"
                      name="enable_auto_characters"
                      tooltip="AI会根据剧情发展自动判断是否需要引入新角色，并自动创建角色卡片和建立关系"
                    >
                      <Radio.Group buttonStyle="solid">
                        <Radio.Button value={true}>启用</Radio.Button>
                        <Radio.Button value={false}>禁用</Radio.Button>
                      </Radio.Group>
                    </Form.Item>
                  )}
                </>
              );
            }}
          </Form.Item>

          {/* 自定义模型选择 - 移到外层，所有模式都显示 */}
          {loadedModels.length > 0 && (
            <Form.Item
              label="AI模型"
              name="model"
              tooltip="选择用于生成的AI模型，不选则使用系统默认模型"
            >
              <Select
                placeholder={defaultModel ? `默认: ${loadedModels.find(m => m.value === defaultModel)?.label || defaultModel}` : "使用默认模型"}
                allowClear
                showSearch
                optionFilterProp="label"
                options={loadedModels}
                onChange={(value) => {
                  console.log('用户在下拉框中选择了模型:', value);
                  // 手动同步到Form
                  generateForm.setFieldsValue({ model: value });
                  console.log('已同步到Form，当前Form值:', generateForm.getFieldsValue());
                }}
              />
              <div style={{ color: '#666', fontSize: 12, marginTop: 4 }}>
                {defaultModel ? `当前默认模型: ${loadedModels.find(m => m.value === defaultModel)?.label || defaultModel}` : '未配置默认模型'}
              </div>
            </Form.Item>
          )}
        </Form>
      ),
      okText: hasOutlines ? '开始续写' : '开始生成',
      cancelText: '取消',
      onOk: async () => {
        const values = await generateForm.validateFields();
        await handleGenerate(values);
      },
    });
  };

  // 手动创建大纲
  const showManualCreateOutlineModal = () => {
    const nextOrderIndex = outlines.length > 0
      ? Math.max(...outlines.map(o => o.order_index)) + 1
      : 1;

    Modal.confirm({
      title: '手动创建大纲',
      width: 600,
      centered: true,
      content: (
        <Form
          form={manualCreateForm}
          layout="vertical"
          initialValues={{ order_index: nextOrderIndex }}
          style={{ marginTop: 16 }}
        >
          <Form.Item
            label="大纲序号"
            name="order_index"
            rules={[{ required: true, message: '请输入序号' }]}
            tooltip={currentProject?.outline_mode === 'one-to-one' ? '在传统模式下，序号即章节编号' : '在细化模式下，序号为卷数'}
          >
            <InputNumber min={1} style={{ width: '100%' }} placeholder="自动计算的下一个序号" />
          </Form.Item>

          <Form.Item
            label="大纲标题"
            name="title"
            rules={[{ required: true, message: '请输入标题' }]}
          >
            <Input placeholder={currentProject?.outline_mode === 'one-to-one' ? '例如：第一章 初入江湖' : '例如：第一卷 初入江湖'} />
          </Form.Item>

          <Form.Item
            label="大纲内容"
            name="content"
            rules={[{ required: true, message: '请输入内容' }]}
          >
            <TextArea
              rows={6}
              placeholder="描述本章/卷的主要情节和发展方向..."
            />
          </Form.Item>
        </Form>
      ),
      okText: '创建',
      cancelText: '取消',
      onOk: async () => {
        const values = await manualCreateForm.validateFields();

        // 校验序号是否重复
        const existingOutline = outlines.find(o => o.order_index === values.order_index);
        if (existingOutline) {
          Modal.warning({
            title: '序号冲突',
            content: (
              <div>
                <p>序号 <strong>{values.order_index}</strong> 已被使用：</p>
                <div style={{
                  padding: 12,
                  background: '#fff7e6',
                  borderRadius: 4,
                  border: '1px solid #ffd591',
                  marginTop: 8
                }}>
                  <div style={{ fontWeight: 500, color: '#fa8c16' }}>
                    {currentProject?.outline_mode === 'one-to-one'
                      ? `第${existingOutline.order_index}章`
                      : `第${existingOutline.order_index}卷`
                    }：{existingOutline.title}
                  </div>
                </div>
                <p style={{ marginTop: 12, color: '#666' }}>
                  💡 建议使用序号 <strong>{nextOrderIndex}</strong>，或选择其他未使用的序号
                </p>
              </div>
            ),
            okText: '我知道了',
            centered: true
          });
          throw new Error('序号重复');
        }

        try {
          await outlineApi.createOutline({
            project_id: currentProject.id,
            ...values
          });
          message.success('大纲创建成功');
          await refreshOutlines();
          manualCreateForm.resetFields();
        } catch (error: any) {
          if (error.message === '序号重复') {
            // 序号重复错误已经显示了Modal，不需要再显示message
            throw error;
          }
          message.error('创建失败：' + (error.message || '未知错误'));
          throw error;
        }
      }
    });
  };

  // 展开单个大纲为多章 - 使用SSE显示进度
  const handleExpandOutline = async (outlineId: string, outlineTitle: string) => {
    try {
      setIsExpanding(true);

      // ✅ 新增：检查是否需要按顺序展开
      const currentOutline = sortedOutlines.find(o => o.id === outlineId);
      if (currentOutline) {
        // 获取所有在当前大纲之前的大纲
        const previousOutlines = sortedOutlines.filter(
          o => o.order_index < currentOutline.order_index
        );

        // 检查前面的大纲是否都已展开
        for (const prevOutline of previousOutlines) {
          try {
            const prevChapters = await outlineApi.getOutlineChapters(prevOutline.id);
            if (!prevChapters.has_chapters) {
              // 如果前面有未展开的大纲，显示提示并阻止操作
              setIsExpanding(false);
              Modal.warning({
                title: '请按顺序展开大纲',
                width: 600,
                centered: true,
                content: (
                  <div>
                    <p style={{ marginBottom: 12 }}>
                      为了保持章节编号的连续性和内容的连贯性，请先展开前面的大纲。
                    </p>
                    <div style={{
                      padding: 12,
                      background: '#fff7e6',
                      borderRadius: 4,
                      border: '1px solid #ffd591'
                    }}>
                      <div style={{ fontWeight: 500, marginBottom: 8, color: '#fa8c16' }}>
                        ⚠️ 需要先展开：
                      </div>
                      <div style={{ color: '#666' }}>
                        第{prevOutline.order_index}卷：《{prevOutline.title}》
                      </div>
                    </div>
                    <p style={{ marginTop: 12, color: '#666', fontSize: 13 }}>
                      💡 提示：您也可以使用「批量展开」功能，系统会自动按顺序处理所有大纲。
                    </p>
                  </div>
                ),
                okText: '我知道了'
              });
              return;
            }
          } catch (error) {
            console.error(`检查大纲 ${prevOutline.id} 失败:`, error);
            // 如果检查失败，继续处理（避免因网络问题阻塞）
          }
        }
      }

      // 第一步：检查是否已有展开的章节
      const existingChapters = await outlineApi.getOutlineChapters(outlineId);

      if (existingChapters.has_chapters && existingChapters.expansion_plans && existingChapters.expansion_plans.length > 0) {
        // 如果已有章节，显示已有的展开规划信息
        setIsExpanding(false);
        showExistingExpansionPreview(outlineTitle, existingChapters);
        return;
      }

      // 如果没有章节，显示展开表单
      setIsExpanding(false);
      Modal.confirm({
        title: (
          <Space>
            <BranchesOutlined />
            <span>展开大纲为多章</span>
          </Space>
        ),
        width: 600,
        centered: true,
        content: (
          <div>
            <div style={{ marginBottom: 16, padding: 12, background: '#f5f5f5', borderRadius: 4 }}>
              <div style={{ fontWeight: 500, marginBottom: 4 }}>大纲标题</div>
              <div style={{ color: '#666' }}>{outlineTitle}</div>
            </div>
            <Form
              form={expansionForm}
              layout="vertical"
              initialValues={{
                target_chapter_count: 3,
                expansion_strategy: 'balanced',
              }}
            >
              <Form.Item
                label="目标章节数"
                name="target_chapter_count"
                rules={[{ required: true, message: '请输入目标章节数' }]}
                tooltip="将这个大纲展开为几章内容"
              >
                <InputNumber
                  min={2}
                  max={10}
                  style={{ width: '100%' }}
                  placeholder="建议2-5章"
                />
              </Form.Item>

              <Form.Item
                label="展开策略"
                name="expansion_strategy"
                tooltip="选择如何分配内容到各章节"
              >
                <Radio.Group>
                  <Radio.Button value="balanced">均衡分配</Radio.Button>
                  <Radio.Button value="climax">高潮重点</Radio.Button>
                  <Radio.Button value="detail">细节丰富</Radio.Button>
                </Radio.Group>
              </Form.Item>
            </Form>
          </div>
        ),
        okText: '生成规划预览',
        cancelText: '取消',
        onOk: async () => {
          try {
            const values = await expansionForm.validateFields();

            // 关闭配置表单
            Modal.destroyAll();

            // 显示SSE进度Modal
            setSSEProgress(0);
            setSSEMessage('正在准备展开大纲...');
            setSSEModalVisible(true);
            setIsExpanding(true);

            // 准备请求数据
            const requestData = {
              ...values,
              auto_create_chapters: false, // 第一步：仅生成规划
              enable_scene_analysis: true
            };

            // 使用SSE客户端调用新的流式端点
            const apiUrl = `/api/outlines/${outlineId}/expand-stream`;
            const client = new SSEPostClient(apiUrl, requestData, {
              onProgress: (msg: string, progress: number) => {
                setSSEMessage(msg);
                setSSEProgress(progress);
              },
              onResult: (data: OutlineExpansionResponse) => {
                console.log('展开完成，结果:', data);
                // 关闭SSE进度Modal
                setSSEModalVisible(false);
                // 显示规划预览
                showExpansionPreview(outlineId, data);
              },
              onError: (error: string) => {
                message.error(`展开失败: ${error}`);
                setSSEModalVisible(false);
                setIsExpanding(false);
              },
              onComplete: () => {
                setSSEModalVisible(false);
                setIsExpanding(false);
              }
            });

            // 开始连接
            client.connect();

          } catch (error) {
            console.error('展开失败:', error);
            message.error('展开失败');
            setSSEModalVisible(false);
            setIsExpanding(false);
          }
        },
      });
    } catch (error) {
      console.error('检查章节失败:', error);
      message.error('检查章节失败');
      setIsExpanding(false);
    }
  };

  // 删除展开的章节内容（保留大纲）
  const handleDeleteExpandedChapters = async (outlineTitle: string, chapters: Array<{ id: string }>) => {
    try {
      // 批量删除所有章节
      const deletePromises = chapters.map(chapter =>
        chapterApi.deleteChapter(chapter.id)
      );
      await Promise.all(deletePromises);

      message.success(`已删除《${outlineTitle}》展开的所有 ${chapters.length} 个章节`);
      await refreshOutlines();
      // 刷新项目信息以更新字数显示
      if (currentProject?.id) {
        const updatedProject = await projectApi.getProject(currentProject.id);
        setCurrentProject(updatedProject);
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除章节失败');
    }
  };

  // 显示已存在章节的展开规划
  const showExistingExpansionPreview = (
    outlineTitle: string,
    data: {
      chapter_count: number;
      chapters: Array<{ id: string; chapter_number: number; title: string }>;
      expansion_plans: Array<{
        sub_index: number;
        title: string;
        plot_summary: string;
        key_events: string[];
        character_focus: string[];
        emotional_tone: string;
        narrative_goal: string;
        conflict_type: string;
        estimated_words: number;
        scenes?: Array<{
          location: string;
          characters: string[];
          purpose: string;
        }> | null;
      }> | null;
    }
  ) => {
    const modal = Modal.info({
      title: (
        <Space style={{ flexWrap: 'wrap' }}>
          <CheckCircleOutlined style={{ color: '#52c41a' }} />
          <span>已存在的展开章节</span>
        </Space>
      ),
      width: isMobile ? '95%' : 900,
      centered: true,
      okText: '关闭',
      style: isMobile ? {
        top: 20,
        maxWidth: 'calc(100vw - 16px)',
        margin: '0 8px'
      } : undefined,
      styles: {
        body: {
          maxHeight: isMobile ? 'calc(100vh - 150px)' : 'calc(80vh - 110px)',
          overflowY: 'auto'
        }
      },
      footer: (_, { OkBtn }) => (
        <Space wrap style={{ width: '100%', justifyContent: isMobile ? 'center' : 'flex-end' }}>
          <Button
            danger
            icon={<DeleteOutlined />}
            onClick={() => {
              modal.destroy();
              Modal.confirm({
                title: '确认删除',
                icon: <ExclamationCircleOutlined />,
                content: (
                  <div>
                    <p>此操作将删除大纲《{outlineTitle}》展开的所有 <strong>{data.chapter_count}</strong> 个章节。</p>
                    <p style={{ color: '#1890ff', marginTop: 8 }}>
                      📝 注意：大纲本身会保留，您可以重新展开
                    </p>
                    <p style={{ color: '#ff4d4f', marginTop: 8 }}>
                      ⚠️ 警告：章节内容将永久删除且无法恢复！
                    </p>
                  </div>
                ),
                okText: '确认删除',
                okType: 'danger',
                cancelText: '取消',
                onOk: () => handleDeleteExpandedChapters(outlineTitle, data.chapters || []),
              });
            }}
            block={isMobile}
            size={isMobile ? 'middle' : undefined}
          >
            删除所有展开的章节 ({data.chapter_count}章)
          </Button>
          <OkBtn />
        </Space>
      ),
      content: (
        <div>
          <div style={{ marginBottom: 16 }}>
            <Space wrap style={{ maxWidth: '100%' }}>
              <Tag
                color="blue"
                style={{
                  whiteSpace: 'normal',
                  wordBreak: 'break-word',
                  height: 'auto',
                  lineHeight: '1.5',
                  padding: '4px 8px'
                }}
              >
                大纲: {outlineTitle}
              </Tag>
              <Tag color="green">章节数: {data.chapter_count}</Tag>
              <Tag color="orange">已创建章节</Tag>
            </Space>
          </div>
          <Tabs
            defaultActiveKey="0"
            type="card"
            items={data.expansion_plans?.map((plan, idx) => ({
              key: idx.toString(),
              label: (
                <Space size="small" style={{ maxWidth: isMobile ? '150px' : 'none' }}>
                  <span
                    style={{
                      fontWeight: 500,
                      whiteSpace: isMobile ? 'normal' : 'nowrap',
                      wordBreak: isMobile ? 'break-word' : 'normal',
                      fontSize: isMobile ? 12 : 14
                    }}
                  >
                    {plan.sub_index}. {plan.title}
                  </span>
                </Space>
              ),
              children: (
                <div style={{ maxHeight: '500px', overflowY: 'auto', padding: '8px 0' }}>
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <Card size="small" title="基本信息">
                      <Space wrap style={{ maxWidth: '100%' }}>
                        <Tag
                          color="blue"
                          style={{
                            whiteSpace: 'normal',
                            wordBreak: 'break-word',
                            height: 'auto',
                            lineHeight: '1.5',
                            padding: '4px 8px'
                          }}
                        >
                          {plan.emotional_tone}
                        </Tag>
                        <Tag
                          color="orange"
                          style={{
                            whiteSpace: 'normal',
                            wordBreak: 'break-word',
                            height: 'auto',
                            lineHeight: '1.5',
                            padding: '4px 8px'
                          }}
                        >
                          {plan.conflict_type}
                        </Tag>
                        <Tag color="green">约{plan.estimated_words}字</Tag>
                      </Space>
                    </Card>

                    <Card size="small" title="情节概要">
                      <div style={{
                        wordBreak: 'break-word',
                        whiteSpace: 'normal',
                        overflowWrap: 'break-word'
                      }}>
                        {plan.plot_summary}
                      </div>
                    </Card>

                    <Card size="small" title="叙事目标">
                      <div style={{
                        wordBreak: 'break-word',
                        whiteSpace: 'normal',
                        overflowWrap: 'break-word'
                      }}>
                        {plan.narrative_goal}
                      </div>
                    </Card>

                    <Card size="small" title="关键事件">
                      <Space direction="vertical" size="small" style={{ width: '100%' }}>
                        {plan.key_events.map((event, eventIdx) => (
                          <div
                            key={eventIdx}
                            style={{
                              wordBreak: 'break-word',
                              whiteSpace: 'normal',
                              overflowWrap: 'break-word'
                            }}
                          >
                            • {event}
                          </div>
                        ))}
                      </Space>
                    </Card>

                    <Card size="small" title="涉及角色">
                      <Space wrap style={{ maxWidth: '100%' }}>
                        {plan.character_focus.map((char, charIdx) => (
                          <Tag
                            key={charIdx}
                            color="purple"
                            style={{
                              whiteSpace: 'normal',
                              wordBreak: 'break-word',
                              height: 'auto',
                              lineHeight: '1.5'
                            }}
                          >
                            {char}
                          </Tag>
                        ))}
                      </Space>
                    </Card>

                    {plan.scenes && plan.scenes.length > 0 && (
                      <Card size="small" title="场景">
                        <Space direction="vertical" size="small" style={{ width: '100%' }}>
                          {plan.scenes.map((scene, sceneIdx) => (
                            <Card
                              key={sceneIdx}
                              size="small"
                              style={{
                                backgroundColor: '#fafafa',
                                maxWidth: '100%',
                                overflow: 'hidden'
                              }}
                            >
                              <div style={{
                                wordBreak: 'break-word',
                                whiteSpace: 'normal',
                                overflowWrap: 'break-word'
                              }}>
                                <strong>地点：</strong>{scene.location}
                              </div>
                              <div style={{
                                wordBreak: 'break-word',
                                whiteSpace: 'normal',
                                overflowWrap: 'break-word'
                              }}>
                                <strong>角色：</strong>{scene.characters.join('、')}
                              </div>
                              <div style={{
                                wordBreak: 'break-word',
                                whiteSpace: 'normal',
                                overflowWrap: 'break-word'
                              }}>
                                <strong>目的：</strong>{scene.purpose}
                              </div>
                            </Card>
                          ))}
                        </Space>
                      </Card>
                    )}
                  </Space>
                </div>
              )
            }))}
          />
        </div>
      ),
    });
  };

  // 显示展开规划预览，并提供确认创建章节的选项
  const showExpansionPreview = (outlineId: string, response: OutlineExpansionResponse) => {
    // 缓存AI生成的规划数据
    const cachedPlans = response.chapter_plans;

    Modal.confirm({
      title: (
        <Space>
          <CheckCircleOutlined style={{ color: '#52c41a' }} />
          <span>展开规划预览</span>
        </Space>
      ),
      width: 900,
      centered: true,
      okText: '确认并创建章节',
      cancelText: '暂不创建',
      content: (
        <div>
          <div style={{ marginBottom: 16 }}>
            <Tag color="blue">策略: {response.expansion_strategy}</Tag>
            <Tag color="green">章节数: {response.actual_chapter_count}</Tag>
            <Tag color="orange">预览模式（未创建章节）</Tag>
          </div>
          <Tabs
            defaultActiveKey="0"
            type="card"
            items={response.chapter_plans.map((plan, idx) => ({
              key: idx.toString(),
              label: (
                <Space size="small">
                  <span style={{ fontWeight: 500 }}>{idx + 1}. {plan.title}</span>
                </Space>
              ),
              children: (
                <div style={{ maxHeight: '500px', overflowY: 'auto', padding: '8px 0' }}>
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <Card size="small" title="基本信息">
                      <Space wrap>
                        <Tag color="blue">{plan.emotional_tone}</Tag>
                        <Tag color="orange">{plan.conflict_type}</Tag>
                        <Tag color="green">约{plan.estimated_words}字</Tag>
                      </Space>
                    </Card>

                    <Card size="small" title="情节概要">
                      {plan.plot_summary}
                    </Card>

                    <Card size="small" title="叙事目标">
                      {plan.narrative_goal}
                    </Card>

                    <Card size="small" title="关键事件">
                      <Space direction="vertical" size="small" style={{ width: '100%' }}>
                        {plan.key_events.map((event, eventIdx) => (
                          <div key={eventIdx}>• {event}</div>
                        ))}
                      </Space>
                    </Card>

                    <Card size="small" title="涉及角色">
                      <Space wrap>
                        {plan.character_focus.map((char, charIdx) => (
                          <Tag key={charIdx} color="purple">{char}</Tag>
                        ))}
                      </Space>
                    </Card>

                    {plan.scenes && plan.scenes.length > 0 && (
                      <Card size="small" title="场景">
                        <Space direction="vertical" size="small" style={{ width: '100%' }}>
                          {plan.scenes.map((scene, sceneIdx) => (
                            <Card key={sceneIdx} size="small" style={{ backgroundColor: '#fafafa' }}>
                              <div><strong>地点：</strong>{scene.location}</div>
                              <div><strong>角色：</strong>{scene.characters.join('、')}</div>
                              <div><strong>目的：</strong>{scene.purpose}</div>
                            </Card>
                          ))}
                        </Space>
                      </Card>
                    )}
                  </Space>
                </div>
              )
            }))}
          />
        </div>
      ),
      onOk: async () => {
        // 第二步：用户确认后，直接使用缓存的规划创建章节（避免重复调用AI）
        await handleConfirmCreateChapters(outlineId, cachedPlans);
      },
      onCancel: () => {
        message.info('已取消创建章节');
      }
    });
  };

  // 确认创建章节 - 使用缓存的规划数据，避免重复AI调用
  const handleConfirmCreateChapters = async (
    outlineId: string,
    cachedPlans: any[]
  ) => {
    try {
      setIsExpanding(true);

      // 使用新的API端点，直接传递缓存的规划数据
      const response = await outlineApi.createChaptersFromPlans(outlineId, cachedPlans);

      message.success(
        `成功创建${response.chapters_created}个章节！`,
        3
      );

      console.log('✅ 使用缓存的规划创建章节，避免了重复的AI调用');

      // 刷新大纲和章节列表
      refreshOutlines();

    } catch (error) {
      console.error('创建章节失败:', error);
      message.error('创建章节失败');
    } finally {
      setIsExpanding(false);
    }
  };

  // 批量展开所有大纲 - 使用SSE流式显示进度
  const handleBatchExpandOutlines = () => {
    if (!currentProject?.id || outlines.length === 0) {
      message.warning('没有可展开的大纲');
      return;
    }

    Modal.confirm({
      title: (
        <Space>
          <AppstoreAddOutlined />
          <span>批量展开所有大纲</span>
        </Space>
      ),
      width: 600,
      centered: true,
      content: (
        <div>
          <div style={{ marginBottom: 16, padding: 12, background: '#fff3cd', borderRadius: 4 }}>
            <div style={{ color: '#856404' }}>
              ⚠️ 将对当前项目的所有 {outlines.length} 个大纲进行展开
            </div>
          </div>
          <Form
            form={batchExpansionForm}
            layout="vertical"
            initialValues={{
              chapters_per_outline: 3,
              expansion_strategy: 'balanced',
            }}
          >
            <Form.Item
              label="每个大纲展开章节数"
              name="chapters_per_outline"
              rules={[{ required: true, message: '请输入章节数' }]}
              tooltip="每个大纲将被展开为几章"
            >
              <InputNumber
                min={2}
                max={10}
                style={{ width: '100%' }}
                placeholder="建议2-5章"
              />
            </Form.Item>

            <Form.Item
              label="展开策略"
              name="expansion_strategy"
            >
              <Radio.Group>
                <Radio.Button value="balanced">均衡分配</Radio.Button>
                <Radio.Button value="climax">高潮重点</Radio.Button>
                <Radio.Button value="detail">细节丰富</Radio.Button>
              </Radio.Group>
            </Form.Item>
          </Form>
        </div>
      ),
      okText: '开始展开',
      cancelText: '取消',
      okButtonProps: { type: 'primary' },
      onOk: async () => {
        try {
          const values = await batchExpansionForm.validateFields();

          // 关闭配置表单
          Modal.destroyAll();

          // 显示SSE进度Modal
          setSSEProgress(0);
          setSSEMessage('正在准备批量展开...');
          setSSEModalVisible(true);
          setIsExpanding(true);

          // 准备请求数据
          const requestData = {
            project_id: currentProject.id,
            ...values,
            auto_create_chapters: false // 第一步：仅生成规划
          };

          // 使用SSE客户端
          const apiUrl = `/api/outlines/batch-expand-stream`;
          const client = new SSEPostClient(apiUrl, requestData, {
            onProgress: (msg: string, progress: number) => {
              setSSEMessage(msg);
              setSSEProgress(progress);
            },
            onResult: (data: any) => {
              console.log('批量展开完成，结果:', data);
              // 缓存AI生成的规划数据
              setCachedBatchExpansionResponse(data);
              setBatchPreviewData(data);
              // 关闭SSE进度Modal
              setSSEModalVisible(false);
              // 重置选择状态
              setSelectedOutlineIdx(0);
              setSelectedChapterIdx(0);
              // 显示批量预览Modal
              setBatchPreviewVisible(true);
            },
            onError: (error: string) => {
              message.error(`批量展开失败: ${error}`);
              setSSEModalVisible(false);
              setIsExpanding(false);
            },
            onComplete: () => {
              setSSEModalVisible(false);
              setIsExpanding(false);
            }
          });

          // 开始连接
          client.connect();

        } catch (error) {
          console.error('批量展开失败:', error);
          message.error('批量展开失败');
          setSSEModalVisible(false);
          setIsExpanding(false);
        }
      },
    });
  };

  // 渲染批量展开预览 Modal 内容
  const renderBatchPreviewContent = () => {
    if (!batchPreviewData) return null;

    return (
      <div>
        {/* 顶部统计信息 */}
        <div style={{ marginBottom: 16 }}>
          <Tag color="blue">已处理: {batchPreviewData.total_outlines_expanded} 个大纲</Tag>
          <Tag color="green">总章节数: {batchPreviewData.expansion_results.reduce((sum: number, r: OutlineExpansionResponse) => sum + r.actual_chapter_count, 0)}</Tag>
          <Tag color="orange">预览模式（未创建章节）</Tag>
          {batchPreviewData.skipped_outlines && batchPreviewData.skipped_outlines.length > 0 && (
            <Tag color="warning">跳过: {batchPreviewData.skipped_outlines.length} 个大纲</Tag>
          )}
        </div>

        {/* 显示跳过的大纲信息 */}
        {batchPreviewData.skipped_outlines && batchPreviewData.skipped_outlines.length > 0 && (
          <div style={{
            marginBottom: 16,
            padding: 12,
            background: '#fffbe6',
            borderRadius: 4,
            border: '1px solid #ffe58f'
          }}>
            <div style={{ fontWeight: 500, marginBottom: 8, color: '#faad14' }}>
              ⚠️ 以下大纲已展开过，已自动跳过：
            </div>
            <Space direction="vertical" size="small" style={{ width: '100%' }}>
              {batchPreviewData.skipped_outlines.map((skipped: any, idx: number) => (
                <div key={idx} style={{ fontSize: 13, color: '#666' }}>
                  • {skipped.outline_title} <Tag color="default" style={{ fontSize: 11 }}>{skipped.reason}</Tag>
                </div>
              ))}
            </Space>
          </div>
        )}

        {/* 水平三栏布局 */}
        <div style={{ display: 'flex', gap: 16, height: 500 }}>
          {/* 左栏：大纲列表 */}
          <div style={{
            width: 280,
            borderRight: '1px solid #f0f0f0',
            paddingRight: 12,
            overflowY: 'auto'
          }}>
            <div style={{ fontWeight: 500, marginBottom: 8, color: '#666' }}>大纲列表</div>
            <List
              size="small"
              dataSource={batchPreviewData.expansion_results}
              renderItem={(result: OutlineExpansionResponse, idx: number) => (
                <List.Item
                  key={idx}
                  onClick={() => {
                    setSelectedOutlineIdx(idx);
                    setSelectedChapterIdx(0);
                  }}
                  style={{
                    cursor: 'pointer',
                    padding: '8px 12px',
                    background: selectedOutlineIdx === idx ? '#e6f7ff' : 'transparent',
                    borderRadius: 4,
                    marginBottom: 4,
                    border: selectedOutlineIdx === idx ? '1px solid #1890ff' : '1px solid transparent'
                  }}
                >
                  <div style={{ width: '100%' }}>
                    <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 4 }}>
                      {idx + 1}. {result.outline_title}
                    </div>
                    <Space size={4}>
                      <Tag color="blue" style={{ fontSize: 11, margin: 0 }}>{result.expansion_strategy}</Tag>
                      <Tag color="green" style={{ fontSize: 11, margin: 0 }}>{result.actual_chapter_count} 章</Tag>
                    </Space>
                  </div>
                </List.Item>
              )}
            />
          </div>

          {/* 中栏：章节列表 */}
          <div style={{
            width: 320,
            borderRight: '1px solid #f0f0f0',
            paddingRight: 12,
            overflowY: 'auto'
          }}>
            <div style={{ fontWeight: 500, marginBottom: 8, color: '#666' }}>
              章节列表 ({batchPreviewData.expansion_results[selectedOutlineIdx]?.actual_chapter_count || 0} 章)
            </div>
            {batchPreviewData.expansion_results[selectedOutlineIdx] && (
              <List
                size="small"
                dataSource={batchPreviewData.expansion_results[selectedOutlineIdx].chapter_plans}
                renderItem={(plan: any, idx: number) => (
                  <List.Item
                    key={idx}
                    onClick={() => setSelectedChapterIdx(idx)}
                    style={{
                      cursor: 'pointer',
                      padding: '8px 12px',
                      background: selectedChapterIdx === idx ? '#e6f7ff' : 'transparent',
                      borderRadius: 4,
                      marginBottom: 4,
                      border: selectedChapterIdx === idx ? '1px solid #1890ff' : '1px solid transparent'
                    }}
                  >
                    <div style={{ width: '100%' }}>
                      <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 4 }}>
                        {idx + 1}. {plan.title}
                      </div>
                      <Space size={4} wrap>
                        <Tag color="blue" style={{ fontSize: 11, margin: 0 }}>{plan.emotional_tone}</Tag>
                        <Tag color="orange" style={{ fontSize: 11, margin: 0 }}>{plan.conflict_type}</Tag>
                        <Tag color="green" style={{ fontSize: 11, margin: 0 }}>约{plan.estimated_words}字</Tag>
                      </Space>
                    </div>
                  </List.Item>
                )}
              />
            )}
          </div>

          {/* 右栏：章节详情 */}
          <div style={{ flex: 1, overflowY: 'auto', paddingLeft: 12 }}>
            <div style={{ fontWeight: 500, marginBottom: 12, color: '#666' }}>章节详情</div>
            {batchPreviewData.expansion_results[selectedOutlineIdx]?.chapter_plans[selectedChapterIdx] ? (
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Card size="small" title="情节概要" bordered={false}>
                  {batchPreviewData.expansion_results[selectedOutlineIdx].chapter_plans[selectedChapterIdx].plot_summary}
                </Card>

                <Card size="small" title="叙事目标" bordered={false}>
                  {batchPreviewData.expansion_results[selectedOutlineIdx].chapter_plans[selectedChapterIdx].narrative_goal}
                </Card>

                <Card size="small" title="关键事件" bordered={false}>
                  <Space direction="vertical" size="small" style={{ width: '100%' }}>
                    {batchPreviewData.expansion_results[selectedOutlineIdx].chapter_plans[selectedChapterIdx].key_events.map((event: string, eventIdx: number) => (
                      <div key={eventIdx}>• {event}</div>
                    ))}
                  </Space>
                </Card>

                <Card size="small" title="涉及角色" bordered={false}>
                  <Space wrap>
                    {batchPreviewData.expansion_results[selectedOutlineIdx].chapter_plans[selectedChapterIdx].character_focus.map((char: string, charIdx: number) => (
                      <Tag key={charIdx} color="purple">{char}</Tag>
                    ))}
                  </Space>
                </Card>

                {batchPreviewData.expansion_results[selectedOutlineIdx].chapter_plans[selectedChapterIdx].scenes && batchPreviewData.expansion_results[selectedOutlineIdx].chapter_plans[selectedChapterIdx].scenes!.length > 0 && (
                  <Card size="small" title="场景" bordered={false}>
                    <Space direction="vertical" size="small" style={{ width: '100%' }}>
                      {batchPreviewData.expansion_results[selectedOutlineIdx].chapter_plans[selectedChapterIdx].scenes!.map((scene: any, sceneIdx: number) => (
                        <Card key={sceneIdx} size="small" style={{ backgroundColor: '#fafafa' }}>
                          <div><strong>地点：</strong>{scene.location}</div>
                          <div><strong>角色：</strong>{scene.characters.join('、')}</div>
                          <div><strong>目的：</strong>{scene.purpose}</div>
                        </Card>
                      ))}
                    </Space>
                  </Card>
                )}
              </Space>
            ) : (
              <Empty description="请选择章节查看详情" />
            )}
          </div>
        </div>
      </div>
    );
  };

  // 处理批量预览确认
  const handleBatchPreviewOk = async () => {
    setBatchPreviewVisible(false);
    await handleConfirmBatchCreateChapters();
  };

  // 处理批量预览取消
  const handleBatchPreviewCancel = () => {
    setBatchPreviewVisible(false);
    message.info('已取消创建章节，规划已保存');
  };


  // 确认批量创建章节 - 使用缓存的规划数据
  const handleConfirmBatchCreateChapters = async () => {
    try {
      setIsExpanding(true);

      // 使用缓存的规划数据，避免重复调用AI
      if (!cachedBatchExpansionResponse) {
        message.error('规划数据丢失，请重新展开');
        return;
      }

      console.log('✅ 使用缓存的批量规划数据创建章节，避免重复AI调用');

      // 逐个大纲创建章节
      let totalCreated = 0;
      const errors: string[] = [];

      for (const result of cachedBatchExpansionResponse.expansion_results) {
        try {
          // 使用create-chapters-from-plans接口，直接传递缓存的规划
          const response = await outlineApi.createChaptersFromPlans(
            result.outline_id,
            result.chapter_plans
          );
          totalCreated += response.chapters_created;
        } catch (error: any) {
          const errorMsg = error.response?.data?.detail || error.message || '未知错误';
          errors.push(`${result.outline_title}: ${errorMsg}`);
          console.error(`创建大纲 ${result.outline_title} 的章节失败:`, error);
        }
      }

      // 显示结果
      if (errors.length === 0) {
        message.success(
          `批量创建完成！共创建 ${totalCreated} 个章节`,
          3
        );
      } else {
        message.warning(
          `部分完成：成功创建 ${totalCreated} 个章节，${errors.length} 个失败`,
          5
        );
        console.error('失败详情:', errors);
      }

      // 清除缓存
      setCachedBatchExpansionResponse(null);

      // 刷新列表
      refreshOutlines();

    } catch (error) {
      console.error('批量创建章节失败:', error);
      message.error('批量创建章节失败');
    } finally {
      setIsExpanding(false);
    }
  };

  // 处理角色确认 - 用户同意创建角色
  const handleConfirmCharacters = async (selectedCharacters: PredictedCharacter[]) => {
    if (!pendingGenerateData) {
      message.error('生成数据丢失，请重新操作');
      return;
    }

    try {
      setCharacterConfirmVisible(false);
      setIsGenerating(true);

      // 显示进度Modal
      setSSEProgress(0);
      setSSEMessage('正在创建确认的角色...');
      setSSEModalVisible(true);

      // 准备请求数据，添加确认的角色
      const requestData = {
        ...pendingGenerateData,
        confirmed_characters: selectedCharacters
      };

      console.log('携带确认角色重新请求:', requestData);

      // 重新发起SSE请求
      const apiUrl = `/api/outlines/generate-stream`;
      const client = new SSEPostClient(apiUrl, requestData, {
        onProgress: (msg: string, progress: number) => {
          setSSEMessage(msg);
          setSSEProgress(progress);
        },
        onResult: (data: any) => {
          console.log('生成完成，结果:', data);
        },
        onError: (error: string) => {
          message.error(`生成失败: ${error}`);
          setSSEModalVisible(false);
          setIsGenerating(false);
        },
        onComplete: () => {
          message.success('大纲生成完成！');
          setSSEModalVisible(false);
          setIsGenerating(false);
          // 清理状态
          setPendingGenerateData(null);
          setCharacterConfirmData(null);
          // 刷新大纲列表
          refreshOutlines();
        }
      });

      client.connect();

    } catch (error) {
      console.error('确认角色失败:', error);
      message.error('操作失败');
      setSSEModalVisible(false);
      setIsGenerating(false);
    }
  };

  // 处理角色确认 - 用户拒绝创建角色
  const handleRejectCharacters = async () => {
    if (!pendingGenerateData) {
      message.error('生成数据丢失，请重新操作');
      return;
    }

    try {
      setCharacterConfirmVisible(false);
      setIsGenerating(true);

      // 显示进度Modal
      setSSEProgress(0);
      setSSEMessage('跳过角色创建，开始续写大纲...');
      setSSEModalVisible(true);

      // 准备请求数据，禁用自动角色引入
      const requestData = {
        ...pendingGenerateData,
        enable_auto_characters: false  // 禁用自动角色引入
      };

      console.log('跳过角色创建，重新请求:', requestData);

      // 重新发起SSE请求
      const apiUrl = `/api/outlines/generate-stream`;
      const client = new SSEPostClient(apiUrl, requestData, {
        onProgress: (msg: string, progress: number) => {
          setSSEMessage(msg);
          setSSEProgress(progress);
        },
        onResult: (data: any) => {
          console.log('生成完成，结果:', data);
        },
        onError: (error: string) => {
          message.error(`生成失败: ${error}`);
          setSSEModalVisible(false);
          setIsGenerating(false);
        },
        onComplete: () => {
          message.success('大纲生成完成！');
          setSSEModalVisible(false);
          setIsGenerating(false);
          // 清理状态
          setPendingGenerateData(null);
          setCharacterConfirmData(null);
          // 刷新大纲列表
          refreshOutlines();
        }
      });

      client.connect();

    } catch (error) {
      console.error('跳过角色创建失败:', error);
      message.error('操作失败');
      setSSEModalVisible(false);
      setIsGenerating(false);
    }
  };

  // 渲染角色确认对话框
  const renderCharacterConfirmModal = () => {
    if (!characterConfirmData) return null;

    return (
      <Modal
        title={
          <Space>
            <ExclamationCircleOutlined style={{ color: '#faad14' }} />
            <span>确认引入新角色</span>
          </Space>
        }
        open={characterConfirmVisible}
        onOk={() => {
          const selectedCharacters = characterConfirmData.predicted_characters.filter(
            (_, idx) => selectedCharacterIndices.includes(idx)
          );
          handleConfirmCharacters(selectedCharacters);
        }}
        onCancel={() => {
          Modal.confirm({
            title: '确认操作',
            content: '是否跳过角色创建，直接续写大纲？',
            okText: '跳过角色，继续续写',
            cancelText: '返回选择',
            onOk: handleRejectCharacters
          });
        }}
        width={800}
        centered
        okText={`确认创建选中的 ${selectedCharacterIndices.length} 个角色`}
        cancelText="跳过角色创建"
      >
        <div>
          <div style={{ marginBottom: 16, padding: 12, background: '#fffbe6', borderRadius: 4, border: '1px solid #ffe58f' }}>
            <div style={{ fontWeight: 500, marginBottom: 8, color: '#d48806' }}>
              AI 分析结果
            </div>
            <div style={{ color: '#666', marginBottom: 8 }}>
              {characterConfirmData.reason}
            </div>
            <Tag color="blue">{characterConfirmData.chapter_range}</Tag>
            <Tag color="green">{characterConfirmData.predicted_characters.length} 个预测角色</Tag>
          </div>

          <div style={{ marginBottom: 12 }}>
            <Space>
              <Button
                size="small"
                onClick={() => setSelectedCharacterIndices(
                  characterConfirmData.predicted_characters.map((_, idx) => idx)
                )}
              >
                全选
              </Button>
              <Button
                size="small"
                onClick={() => setSelectedCharacterIndices([])}
              >
                全不选
              </Button>
            </Space>
          </div>

          <List
            dataSource={characterConfirmData.predicted_characters}
            renderItem={(character, index) => (
              <List.Item
                key={index}
                style={{
                  background: selectedCharacterIndices.includes(index) ? '#f0f5ff' : 'transparent',
                  padding: 12,
                  borderRadius: 4,
                  marginBottom: 8,
                  border: selectedCharacterIndices.includes(index) ? '1px solid #1890ff' : '1px solid #f0f0f0',
                  cursor: 'pointer'
                }}
                onClick={() => {
                  if (selectedCharacterIndices.includes(index)) {
                    setSelectedCharacterIndices(selectedCharacterIndices.filter(i => i !== index));
                  } else {
                    setSelectedCharacterIndices([...selectedCharacterIndices, index]);
                  }
                }}
              >
                <div style={{ width: '100%' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <Space>
                      <input
                        type="checkbox"
                        checked={selectedCharacterIndices.includes(index)}
                        onChange={() => { }}
                        style={{ cursor: 'pointer' }}
                      />
                      <span style={{ fontWeight: 500, fontSize: 16 }}>
                        {character.name || character.role_description}
                      </span>
                      <Tag color="blue">{character.suggested_role_type}</Tag>
                      <Tag color="orange">{character.importance}</Tag>
                    </Space>
                    <Tag>第{character.appearance_chapter}章登场</Tag>
                  </div>

                  <div style={{ marginBottom: 8, color: '#666' }}>
                    <strong>剧情作用：</strong>{character.plot_function}
                  </div>

                  {character.key_abilities && character.key_abilities.length > 0 && (
                    <div style={{ marginBottom: 8 }}>
                      <strong>关键能力：</strong>
                      <Space wrap style={{ marginLeft: 8 }}>
                        {character.key_abilities.map((ability, idx) => (
                          <Tag key={idx} color="purple">{ability}</Tag>
                        ))}
                      </Space>
                    </div>
                  )}

                  {character.relationship_suggestions && character.relationship_suggestions.length > 0 && (
                    <div>
                      <strong>建议关系：</strong>
                      <Space wrap style={{ marginLeft: 8 }}>
                        {character.relationship_suggestions.map((rel, idx) => (
                          <Tag key={idx} color="cyan">
                            {rel.target_character_name} - {rel.relationship_type}
                          </Tag>
                        ))}
                      </Space>
                    </div>
                  )}
                </div>
              </List.Item>
            )}
          />
        </div>
      </Modal>
    );
  };

  return (
    <>
      {/* 角色确认对话框 */}
      {renderCharacterConfirmModal()}

      {/* 批量展开预览 Modal */}
      <Modal
        title={
          <Space>
            <CheckCircleOutlined style={{ color: '#52c41a' }} />
            <span>批量展开规划预览</span>
          </Space>
        }
        open={batchPreviewVisible}
        onOk={handleBatchPreviewOk}
        onCancel={handleBatchPreviewCancel}
        width={1200}
        centered
        okText="确认并批量创建章节"
        cancelText="暂不创建"
        okButtonProps={{ danger: true }}
      >
        {renderBatchPreviewContent()}
      </Modal>

      {/* SSE进度Modal - 使用统一组件 */}
      <SSEProgressModal
        visible={sseModalVisible}
        progress={sseProgress}
        message={sseMessage}
        title="AI生成中..."
      />

      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        {/* 固定头部 */}
        <div style={{
          position: 'sticky',
          top: 0,
          zIndex: 10,
          backgroundColor: '#fff',
          padding: isMobile ? '12px 0' : '16px 0',
          marginBottom: isMobile ? 12 : 16,
          borderBottom: '1px solid #f0f0f0',
          display: 'flex',
          flexDirection: isMobile ? 'column' : 'row',
          gap: isMobile ? 12 : 0,
          justifyContent: 'space-between',
          alignItems: isMobile ? 'stretch' : 'center'
        }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <h2 style={{ margin: 0, fontSize: isMobile ? 18 : 24 }}>故事大纲</h2>
            {currentProject?.outline_mode && (
              <Tag color={currentProject.outline_mode === 'one-to-one' ? 'blue' : 'green'} style={{ width: 'fit-content' }}>
                {currentProject.outline_mode === 'one-to-one' ? '传统模式 (1→1)' : '细化模式 (1→N)'}
              </Tag>
            )}
          </div>
          <Space size="small" wrap={isMobile}>
            <Button
              icon={<PlusOutlined />}
              onClick={showManualCreateOutlineModal}
              block={isMobile}
            >
              手动创建
            </Button>
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              onClick={showGenerateModal}
              loading={isGenerating}
              block={isMobile}
            >
              {isMobile ? 'AI生成/续写' : 'AI生成/续写大纲'}
            </Button>
            {outlines.length > 0 && currentProject?.outline_mode === 'one-to-many' && (
              <Tooltip title="将所有大纲展开为多章，实现从大纲到章节的一对多关系">
                <Button
                  icon={<AppstoreAddOutlined />}
                  onClick={handleBatchExpandOutlines}
                  loading={isExpanding}
                  disabled={isGenerating}
                >
                  {isMobile ? '批量展开' : '批量展开为多章'}
                </Button>
              </Tooltip>
            )}
          </Space>
        </div>

        {/* 可滚动内容区域 */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {outlines.length === 0 ? (
            <Empty description="还没有大纲，开始创建吧！" />
          ) : (
            <Card style={cardStyles.base}>
              <List
                dataSource={sortedOutlines}
                renderItem={(item) => (
                  <List.Item
                    style={{
                      padding: '16px 0',
                      borderRadius: 8,
                      transition: 'background 0.3s ease',
                      flexDirection: isMobile ? 'column' : 'row',
                      alignItems: isMobile ? 'flex-start' : 'center'
                    }}
                    actions={isMobile ? undefined : [
                      ...(currentProject?.outline_mode === 'one-to-many' ? [
                        <Tooltip title="展开为多章">
                          <Button
                            type="text"
                            icon={<BranchesOutlined />}
                            onClick={() => handleExpandOutline(item.id, item.title)}
                            loading={isExpanding}
                          >
                            展开
                          </Button>
                        </Tooltip>
                      ] : []), // 一对一模式：不显示任何展开/创建按钮
                      <Button
                        type="text"
                        icon={<EditOutlined />}
                        onClick={() => handleOpenEditModal(item.id)}
                      >
                        编辑
                      </Button>,
                      <Popconfirm
                        title="确定删除这条大纲吗？"
                        onConfirm={() => handleDeleteOutline(item.id)}
                        okText="确定"
                        cancelText="取消"
                      >
                        <Button type="text" danger icon={<DeleteOutlined />}>
                          删除
                        </Button>
                      </Popconfirm>,
                    ]}
                  >
                    <div style={{ width: '100%' }}>
                      <List.Item.Meta
                        title={
                          <Space size="small" style={{ fontSize: isMobile ? 14 : 16, flexWrap: 'wrap' }}>
                            <span style={{ color: '#1890ff', fontWeight: 'bold' }}>
                              {currentProject?.outline_mode === 'one-to-one'
                                ? `第${item.order_index || '?'}章`
                                : `第${item.order_index || '?'}卷`
                              }
                            </span>
                            <span>{item.title}</span>
                            {/* ✅ 新增：展开状态标识 - 仅在一对多模式显示 */}
                            {currentProject?.outline_mode === 'one-to-many' && (
                              outlineExpandStatus[item.id] ? (
                                <Tag color="success" icon={<CheckCircleOutlined />}>已展开</Tag>
                              ) : (
                                <Tag color="default">未展开</Tag>
                              )
                            )}
                          </Space>
                        }
                        description={
                          <div style={{ fontSize: isMobile ? 12 : 14 }}>
                            {item.content}
                          </div>
                        }
                      />

                      {/* 移动端：按钮显示在内容下方 */}
                      {isMobile && (
                        <Space style={{ marginTop: 12, width: '100%', justifyContent: 'flex-end' }} wrap>
                          <Button
                            type="text"
                            icon={<EditOutlined />}
                            onClick={() => handleOpenEditModal(item.id)}
                            size="small"
                          />
                          {/* 一对多模式：显示展开按钮 */}
                          {currentProject?.outline_mode === 'one-to-many' && (
                            <Tooltip title="展开为多章">
                              <Button
                                type="text"
                                icon={<BranchesOutlined />}
                                onClick={() => handleExpandOutline(item.id, item.title)}
                                loading={isExpanding}
                                size="small"
                              />
                            </Tooltip>
                          )}
                          {/* 一对一模式：不显示任何展开/创建按钮 */}
                          <Popconfirm
                            title="确定删除这条大纲吗？"
                            onConfirm={() => handleDeleteOutline(item.id)}
                            okText="确定"
                            cancelText="取消"
                          >
                            <Button type="text" danger icon={<DeleteOutlined />} size="small" />
                          </Popconfirm>
                        </Space>
                      )}
                    </div>
                  </List.Item>
                )}
              />
            </Card>
          )}
        </div>
      </div>
    </>
  );
}