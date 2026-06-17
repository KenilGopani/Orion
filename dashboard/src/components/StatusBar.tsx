import type { HealthResponse } from "../api/orion";

interface StatusBarProps {
  health: HealthResponse | null;
}

export default function StatusBar({ health }: StatusBarProps) {
  const isOnline = health?.status === "ok";
  const openclawOk = health?.dependencies?.openclaw ?? false;

  return (
    <header className="status-bar">
      <div className="status-bar__left">
        <span className="status-bar__logo">ORION</span>
        <div className="status-bar__indicator">
          <span
            className={`status-bar__dot ${
              isOnline ? "status-bar__dot--online" : "status-bar__dot--offline"
            }`}
          />
          {isOnline ? "Online" : "Offline"}
        </div>
        <div className="status-bar__indicator">
          <span
            className={`status-bar__dot ${
              openclawOk ? "status-bar__dot--online" : "status-bar__dot--offline"
            }`}
          />
          OpenClaw
        </div>
      </div>

      <div className="status-bar__right">
        {health?.dev_mode && (
          <span className="status-bar__badge status-bar__badge--dev">Dev Mode</span>
        )}
        {health?.mock_openclaw && (
          <span className="status-bar__badge status-bar__badge--mock">Mock</span>
        )}
        {health?.providers && (
          <>
            <span className="status-bar__provider" title="STT Provider">
              🎤 {health.providers.stt}
            </span>
            <span className="status-bar__provider" title="LLM Provider">
              🧠 {health.providers.llm}
            </span>
            <span className="status-bar__provider" title="TTS Provider">
              🔊 {health.providers.tts}
            </span>
          </>
        )}
      </div>
    </header>
  );
}
