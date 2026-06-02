import { Input } from 'antd';

import { samplePrompt } from '../../lib/workbenchConstants';

type PromptBarProps = {
  prompt: string;
  onPromptChange: (value: string) => void;
};

export function PromptBar({ prompt, onPromptChange }: PromptBarProps) {
  return (
    <section className="prompt-bar" aria-label="自然语言用例生成器">
      <div className="prompt-input-panel">
        <Input.TextArea
          className="prompt-textarea"
          aria-label="自然语言生成用例"
          placeholder={samplePrompt}
          value={prompt}
          onChange={(event) => onPromptChange(event.target.value)}
        />
      </div>
    </section>
  );
}
