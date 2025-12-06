import { useState } from 'react';
import { FloatButton } from 'antd';
import { FileTextOutlined } from '@ant-design/icons';
import ChangelogModal from './ChangelogModal';

export default function ChangelogFloatingButton() {
  const [showChangelog, setShowChangelog] = useState(false);

  return (
    <div style={{ position: 'fixed', zIndex: 9999 }}>
      <FloatButton
        icon={<FileTextOutlined />}
        type="primary"
        tooltip="查看更新日志"
        style={{
          right: 24,
          bottom: 100,
        }}
        onClick={() => setShowChangelog(true)}
      />

      <ChangelogModal
        visible={showChangelog}
        onClose={() => setShowChangelog(false)}
      />
    </div>
  );
}