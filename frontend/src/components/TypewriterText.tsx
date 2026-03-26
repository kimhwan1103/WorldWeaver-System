import { useState, useEffect, useRef } from "react";

interface Props {
  text: string;
  speed?: number;
  onComplete?: () => void;
  className?: string;
}

export default function TypewriterText({ text, speed = 30, onComplete, className }: Props) {
  const [displayed, setDisplayed] = useState("");
  const [done, setDone] = useState(false);
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    if (!text) {
      setDisplayed("");
      setDone(true);
      onCompleteRef.current?.();
      return;
    }

    setDisplayed("");
    setDone(false);
    let i = 0;
    const timer = setInterval(() => {
      i++;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) {
        clearInterval(timer);
        setDone(true);
        onCompleteRef.current?.();
      }
    }, speed);
    return () => clearInterval(timer);
  }, [text, speed]);

  return (
    <span className={className}>
      {displayed}
      {!done && <span className="typewriter-cursor">|</span>}
    </span>
  );
}
