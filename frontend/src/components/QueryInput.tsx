import { useState, FormEvent } from 'react';

interface QueryInputProps {
  onSubmit: (question: string) => void;
  isLoading: boolean;
}

export function QueryInput({ onSubmit, isLoading }: QueryInputProps) {
  const [question, setQuestion] = useState('');

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (question.trim() && !isLoading) {
      onSubmit(question.trim());
    }
  };

  const exampleQueries = [
    'Do ACE inhibitors reduce mortality in heart failure?',
    'What is the efficacy of metformin for type 2 diabetes?',
    'Are statins effective for primary prevention of cardiovascular disease?',
  ];

  return (
    <div className="w-full">
      <form onSubmit={handleSubmit} className="relative">
        <div className="relative">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask a medical question..."
            disabled={isLoading}
            rows={3}
            className="w-full px-5 py-4 pr-24 text-lg rounded-2xl 
                       bg-surface-elevated border border-surface-hover
                       text-text-primary placeholder:text-text-muted
                       focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent
                       disabled:opacity-50 disabled:cursor-not-allowed
                       resize-none transition-all duration-200"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
          />
          <button
            type="submit"
            disabled={!question.trim() || isLoading}
            className="absolute right-3 bottom-3 px-5 py-2.5 rounded-xl
                       bg-accent hover:bg-accent-hover
                       text-white font-semibold text-sm
                       disabled:opacity-40 disabled:cursor-not-allowed
                       transition-all duration-200 
                       flex items-center gap-2"
          >
            {isLoading ? (
              <>
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                    fill="none"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
                Analyzing...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                Analyze
              </>
            )}
          </button>
        </div>
      </form>

      {/* Example queries */}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="text-text-muted text-sm leading-none">Try:</span>
        {exampleQueries.map((query, i) => (
          <button
            key={i}
            onClick={() => setQuestion(query)}
            disabled={isLoading}
            className="text-sm px-3 py-1.5 rounded-lg
                       bg-surface-hover/50 text-text-secondary
                       hover:bg-surface-hover hover:text-text-primary
                       disabled:opacity-50 disabled:cursor-not-allowed
                       transition-all duration-150"
          >
            {query.length > 40 ? query.slice(0, 40) + '...' : query}
          </button>
        ))}
      </div>
    </div>
  );
}
