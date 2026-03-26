import ReactMarkdown from "react-markdown";

interface Props {
  text: string;
  className?: string;
  inline?: boolean;
}

export default function MarkdownText({ text, className, inline }: Props) {
  const Wrapper = inline ? "span" : "div";
  return (
    <Wrapper className={className}>
      <ReactMarkdown
        components={{
          p: ({ children }) => inline ? <span>{children}</span> : <p>{children}</p>,
          strong: ({ children }) => <strong>{children}</strong>,
          em: ({ children }) => <em>{children}</em>,
        }}
      >
        {text}
      </ReactMarkdown>
    </Wrapper>
  );
}
