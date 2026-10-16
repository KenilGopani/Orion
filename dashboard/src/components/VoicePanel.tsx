import { useEffect, useRef, useState } from "react";
import type { RemoteTrack, Room } from "livekit-client";
import { orionApi } from "../api/orion";

type Status = "idle" | "connecting" | "connected" | "error";

/**
 * Talk to Orion from the dashboard: joins the voice room with your microphone
 * and plays the agent's replies. Works against LiveKit Cloud or, in offline
 * mode, the local LiveKit server. livekit-client is bundled (no CDN) and
 * loaded only when you start talking, keeping the dashboard itself light.
 */
export default function VoicePanel() {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const [agentPresent, setAgentPresent] = useState(false);
  const roomRef = useRef<Room | null>(null);
  const audioRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => () => void roomRef.current?.disconnect(), []);

  const connect = async () => {
    setStatus("connecting");
    setError(null);
    try {
      const [{ url, token }, { Room, RoomEvent, Track }] = await Promise.all([
        orionApi.getVoiceToken(),
        import("livekit-client"),
      ]);
      const room = new Room({ adaptiveStream: true, dynacast: true });
      roomRef.current = room;

      room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
        if (track.kind === Track.Kind.Audio) {
          audioRef.current?.appendChild(track.attach());
        }
      });
      room.on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
        track.detach().forEach((el) => el.remove());
      });
      room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
        setAgentSpeaking(speakers.some((p) => p.identity !== room.localParticipant.identity));
      });
      const updatePresence = () => setAgentPresent(room.remoteParticipants.size > 0);
      room.on(RoomEvent.ParticipantConnected, updatePresence);
      room.on(RoomEvent.ParticipantDisconnected, updatePresence);
      room.on(RoomEvent.Disconnected, () => {
        setStatus("idle");
        setAgentPresent(false);
        setAgentSpeaking(false);
      });

      await room.connect(url, token);
      await room.localParticipant.setMicrophoneEnabled(true);
      updatePresence();
      setStatus("connected");
    } catch (err) {
      setError((err as Error).message);
      setStatus("error");
      await roomRef.current?.disconnect();
      roomRef.current = null;
    }
  };

  const disconnect = async () => {
    await roomRef.current?.disconnect();
    roomRef.current = null;
    setStatus("idle");
  };

  const hint =
    status === "connected"
      ? agentPresent
        ? agentSpeaking
          ? "Orion is speaking…"
          : "Listening. Go ahead."
        : "Connected. Waiting for the voice agent to join…"
      : status === "connecting"
        ? "Connecting…"
        : "Talk to Orion from this browser.";

  return (
    <div className="panel" id="voice-panel">
      <div className="panel__header">
        <span className="panel__title">Talk</span>
        {status === "connected" && (
          <span className={`voice-dot ${agentSpeaking ? "voice-dot--speaking" : ""}`} aria-hidden="true" />
        )}
      </div>
      <div className="panel__body voice-panel">
        <p className="voice-panel__hint">{hint}</p>
        {error && <p className="voice-panel__error">{error}</p>}
        {status === "connected" ? (
          <button className="btn btn--reject" onClick={disconnect} id="voice-disconnect">
            End conversation
          </button>
        ) : (
          <button
            className="btn btn--approve"
            onClick={connect}
            disabled={status === "connecting"}
            id="voice-connect"
          >
            {status === "connecting" ? "Connecting…" : "Start talking"}
          </button>
        )}
        <div ref={audioRef} hidden />
      </div>
    </div>
  );
}
