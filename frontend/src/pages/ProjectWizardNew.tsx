import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Form, Input, InputNumber, Select, Button, Card,
  Row, Col, Typography, Space, message
} from 'antd';
import {
  RocketOutlined, ArrowLeftOutlined
} from '@ant-design/icons';
import { AIProjectGenerator, type GenerationConfig } from '../components/AIProjectGenerator';
import type { WizardBasicInfo } from '../types';

const { TextArea } = Input;
const { Title, Paragraph } = Typography;

export default function ProjectWizardNew() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [form] = Form.useForm();
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);
  
  // 状态管理
  const [currentStep, setCurrentStep] = useState<'form' | 'generating'>('form');
  const [generationConfig, setGenerationConfig] = useState<GenerationConfig | null>(null);
  const [resumeProjectId, setResumeProjectId] = useState<string | null>(null);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth <= 768);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // 检查URL参数,如果有project_id则恢复生成
  useEffect(() => {
    const projectId = searchParams.get('project_id');
    if (projectId) {
      setResumeProjectId(projectId);
      handleResumeGeneration(projectId);
    }
  }, [searchParams]);

  // 恢复未完成项目的生成
  const handleResumeGeneration = async (projectId: string) => {
    try {
      const response = await fetch(`/api/projects/${projectId}`, {
        credentials: 'include'
      });
      if (!response.ok) {
        throw new Error('获取项目信息失败');
      }
      const project = await response.json();
      
      const config: GenerationConfig = {
        title: project.title,
        description: project.description || '',
        theme: project.theme || '',
        genre: project.genre || '',
        narrative_perspective: project.narrative_perspective || '第三人称',
        target_words: project.target_words || 100000,
        chapter_count: 3,
        character_count: project.character_count || 5,
      };
      
      setGenerationConfig(config);
      setCurrentStep('generating');
    } catch (error) {
      console.error('恢复生成失败:', error);
      message.error('恢复生成失败,请重试');
      navigate('/');
    }
  };

  // 开始生成流程
  const handleAutoGenerate = async (values: WizardBasicInfo) => {
    const config: GenerationConfig = {
      title: values.title,
      description: values.description,
      theme: values.theme,
      genre: values.genre,
      narrative_perspective: values.narrative_perspective,
      target_words: values.target_words || 100000,
      chapter_count: 3, // 默认生成3章大纲
      character_count: values.character_count || 5,
    };
    
    setGenerationConfig(config);
    setCurrentStep('generating');
  };

  // 生成完成回调
  const handleComplete = (projectId: string) => {
    console.log('项目创建完成:', projectId);
  };

  // 返回表单页面
  const handleBack = () => {
    setCurrentStep('form');
    setGenerationConfig(null);
  };

  // 渲染表单页面
  const renderForm = () => (
    <Card>
      <Title level={isMobile ? 4 : 3} style={{ marginBottom: 24 }}>
        创建新项目
      </Title>
      <Paragraph type="secondary" style={{ marginBottom: 32 }}>
        填写基本信息后，AI将自动为您生成世界观、角色和大纲节点（大纲可在项目内手动展开为章节）
      </Paragraph>

      <Form
        form={form}
        layout="vertical"
        onFinish={handleAutoGenerate}
        initialValues={{
          genre: ['玄幻'],
          chapter_count: 30,
          narrative_perspective: '第三人称',
          character_count: 5,
          target_words: 100000,
        }}
      >
        <Form.Item
          label="书名"
          name="title"
          rules={[{ required: true, message: '请输入书名' }]}
        >
          <Input placeholder="输入你的小说标题" size="large" />
        </Form.Item>

        <Form.Item
          label="小说简介"
          name="description"
          rules={[{ required: true, message: '请输入小说简介' }]}
        >
          <TextArea
            rows={3}
            placeholder="用一段话介绍你的小说..."
            showCount
            maxLength={300}
          />
        </Form.Item>

        <Form.Item
          label="主题"
          name="theme"
          rules={[{ required: true, message: '请输入主题' }]}
        >
          <TextArea
            rows={4}
            placeholder="描述你的小说主题..."
            showCount
            maxLength={500}
          />
        </Form.Item>

        <Form.Item
          label="类型"
          name="genre"
          rules={[{ required: true, message: '请选择小说类型' }]}
        >
          <Select
            mode="tags"
            placeholder="选择或输入类型标签（如：玄幻、都市、修仙）"
            size="large"
            tokenSeparators={[',']}
            maxTagCount={5}
          >
            <Select.Option value="玄幻">玄幻</Select.Option>
            <Select.Option value="都市">都市</Select.Option>
            <Select.Option value="历史">历史</Select.Option>
            <Select.Option value="科幻">科幻</Select.Option>
            <Select.Option value="武侠">武侠</Select.Option>
            <Select.Option value="仙侠">仙侠</Select.Option>
            <Select.Option value="奇幻">奇幻</Select.Option>
            <Select.Option value="悬疑">悬疑</Select.Option>
            <Select.Option value="言情">言情</Select.Option>
            <Select.Option value="修仙">修仙</Select.Option>
          </Select>
        </Form.Item>

        <Row gutter={16}>
          <Col xs={24} sm={12}>
            <Form.Item
              label="叙事视角"
              name="narrative_perspective"
              rules={[{ required: true, message: '请选择叙事视角' }]}
            >
              <Select size="large" placeholder="选择小说的叙事视角">
                <Select.Option value="第一人称">第一人称</Select.Option>
                <Select.Option value="第三人称">第三人称</Select.Option>
                <Select.Option value="全知视角">全知视角</Select.Option>
              </Select>
            </Form.Item>
          </Col>
          <Col xs={24} sm={12}>
            <Form.Item
              label="角色数量"
              name="character_count"
              rules={[{ required: true, message: '请输入角色数量' }]}
            >
              <InputNumber
                min={3}
                max={20}
                style={{ width: '100%' }}
                size="large"
                addonAfter="个"
                placeholder="AI生成的角色数量"
              />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item
          label="目标字数"
          name="target_words"
          rules={[{ required: true, message: '请输入目标字数' }]}
        >
          <InputNumber
            min={10000}
            style={{ width: '100%' }}
            size="large"
            addonAfter="字"
            placeholder="整部小说的目标字数"
          />
        </Form.Item>

        <Form.Item>
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Button
              type="primary"
              htmlType="submit"
              size="large"
              block
              icon={<RocketOutlined />}
            >
              开始创建项目
            </Button>
            <Button
              size="large"
              block
              onClick={() => navigate('/')}
            >
              返回首页
            </Button>
          </Space>
        </Form.Item>
      </Form>
    </Card>
  );

  return (
    <div style={{
      minHeight: '100vh',
      background: currentStep === 'generating' 
        ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
        : '#f5f7fa',
    }}>
      {/* 顶部标题栏 - 固定不滚动 */}
      <div style={{
        position: 'sticky',
        top: 0,
        zIndex: 100,
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
      }}>
        <div style={{
          maxWidth: 1200,
          margin: '0 auto',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: isMobile ? '12px 16px' : '16px 24px',
        }}>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/')}
            size={isMobile ? 'middle' : 'large'}
            disabled={currentStep === 'generating'}
            style={{
              background: 'rgba(255,255,255,0.2)',
              borderColor: 'rgba(255,255,255,0.3)',
              color: '#fff',
            }}
          >
            {isMobile ? '返回' : '返回首页'}
          </Button>
          
          <Title level={isMobile ? 4 : 2} style={{
            margin: 0,
            color: '#fff',
            textShadow: '0 2px 4px rgba(0,0,0,0.1)',
          }}>
            项目创建向导
          </Title>
          
          <div style={{ width: isMobile ? 60 : 120 }}></div>
        </div>
      </div>

      {/* 内容区域 */}
      <div style={{
        maxWidth: 800,
        margin: '0 auto',
        padding: isMobile ? '16px 12px' : '24px 24px',
      }}>
        {currentStep === 'form' && renderForm()}
        {currentStep === 'generating' && generationConfig && (
          <AIProjectGenerator
            config={generationConfig}
            storagePrefix="wizard"
            onComplete={handleComplete}
            onBack={handleBack}
            isMobile={isMobile}
            resumeProjectId={resumeProjectId || undefined}
          />
        )}
      </div>
    </div>
  );
}