import { useEffect, useRef } from "react";
import type { ConversationMessage } from "../api/orion";

interface ConversationLogProps {
  messages: ConversationMessage[];
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function ConversationLog({ messages }: ConversationLogProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  return (
    <div className="panel conversation-panel" id="conversation-panel">
      <div className="panel__header">
        <span className="panel__title">Conversation Log</span>
        {messages.length > 0 && (
          <span className="panel__count">{messages.length}</span>
        )}
      </div>
      <div className="panel__body">
        {messages.length === 0 ? (
          <div className="panel__empty">
            No conversations yet — speak to Orion or use the text agent
          </div>
        ) : (
          <div className="conversation-log">
            {messages.map((msg) => (
              <div key={msg.id} className="conv-message">
                <div
                  className={`conv-message__avatar conv-message__avatar--${msg.role}`}
                >
                  {msg.role === "user" ? "U" : "O"}
                </div>
                <div className="conv-message__content">
                  <div className={`conv-message__role conv-message__role--${msg.role}`}>
                    {msg.role === "user" ? "You" : "Orion"}
                  </div>
                  <div className="conv-message__text">{msg.content}</div>
                </div>
                <span className="conv-message__time">
                  {formatTime(msg.timestamp)}
                </span>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
    </div>
  );
}
