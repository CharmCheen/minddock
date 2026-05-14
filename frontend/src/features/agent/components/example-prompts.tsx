import React from 'react';

interface ExamplePromptsProps {
  taskType: 'auto' | 'chat' | 'summarize' | 'compare';
  onSelect: (prompt: string) => void;
}

export const ExamplePrompts: React.FC<ExamplePromptsProps> = ({ taskType, onSelect }) => {
  const examples = {
    auto: [
      "Can you explain the main concepts discussed in the selected document?",
      "Compare the methodologies proposed in the two selected sources."
    ],
    chat: [
      "What does this source say about the system architecture?",
      "Which evidence supports this conclusion?",
      "Where is this design choice mentioned in the documents?"
    ],
    summarize: [
      "Summarize the main ideas of the selected sources.",
      "Extract the key design points from these documents.",
      "Give me a concise chapter-style summary."
    ],
    compare: [
      "Compare these sources in terms of system design.",
      "What are the common points and differences?",
      "Are there any conflicting claims between these documents?"
    ]
  };

  const currentExamples = examples[taskType];

  return (
    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '8px', padding: '0 24px', justifyContent: 'center' }}>
      {currentExamples.map((ex, i) => (
        <div
          key={i}
          onClick={() => onSelect(ex)}
          style={{
            fontSize: '12px',
            color: 'var(--color-brand-600)',
            background: 'var(--color-brand-50)',
            border: '1px solid var(--color-brand-200)',
            padding: '6px 14px',
            borderRadius: 'var(--radius-full)',
            cursor: 'pointer',
            transition: 'all var(--transition-fast)',
            whiteSpace: 'normal',
            lineHeight: '1.4',
            maxWidth: '100%',
            fontWeight: 500,
          }}
          onMouseOver={(e) => {
            e.currentTarget.style.background = 'var(--color-brand-100)';
            e.currentTarget.style.borderColor = 'var(--color-brand-500)';
            e.currentTarget.style.boxShadow = 'var(--shadow-sm)';
          }}
          onMouseOut={(e) => {
            e.currentTarget.style.background = 'var(--color-brand-50)';
            e.currentTarget.style.borderColor = 'var(--color-brand-200)';
            e.currentTarget.style.boxShadow = 'none';
          }}
        >
          {ex}
        </div>
      ))}
    </div>
  );
};
