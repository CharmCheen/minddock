import React from 'react';

interface ExamplePromptsProps {
  taskType: 'chat' | 'summarize' | 'compare';
  onSelect: (prompt: string) => void;
}

export const ExamplePrompts: React.FC<ExamplePromptsProps> = ({ taskType, onSelect }) => {
  const examples = {
    chat: [
      "Can you explain the main concepts discussed in the selected document?",
      "What are the key takeaways from this source for a beginner?"
    ],
    summarize: [
      "Generate a comprehensive summary of the current document.",
      "Summarize the technical architecture mentioned here."
    ],
    compare: [
      "Compare the methodologies proposed in the two selected sources.",
      "What are the common points and conflicts between these views?"
    ]
  };

  const currentExamples = examples[taskType];

  return (
    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '8px', padding: '0 24px' }}>
      {currentExamples.map((ex, i) => (
        <div 
          key={i}
          onClick={() => onSelect(ex)}
          style={{
            fontSize: '12px',
            color: '#3b82f6',
            background: '#eff6ff',
            border: '1px solid #bfdbfe',
            padding: '6px 12px',
            borderRadius: '16px',
            cursor: 'pointer',
            transition: 'all 0.2s ease',
            whiteSpace: 'normal',
            lineHeight: '1.4',
            maxWidth: '100%',
          }}
          onMouseOver={(e) => e.currentTarget.style.background = '#dbeafe'}
          onMouseOut={(e) => e.currentTarget.style.background = '#eff6ff'}
        >
          {ex}
        </div>
      ))}
    </div>
  );
};
