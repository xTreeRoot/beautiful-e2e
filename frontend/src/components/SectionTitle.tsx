import type { ReactNode } from 'react';
import { Flex, Typography } from 'antd';

const { Text } = Typography;

type SectionTitleProps = {
  icon: ReactNode;
  title: string;
  extra?: ReactNode;
};

export function SectionTitle({ icon, title, extra }: SectionTitleProps) {
  return (
    <Flex className="section-title" align="center" gap={8}>
      {icon}
      <Text strong>{title}</Text>
      {extra}
    </Flex>
  );
}
