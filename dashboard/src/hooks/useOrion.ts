/**
 * Custom hooks for polling Orion API data.
 * Uses simple setInterval-based polling instead of a heavy library.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import {
  orionApi,
  type HealthResponse,
  type Task,
  type ConversationMessage,
  type RuntimeEvent,
} from "../api/orion";

// ── useHealth ────────────────────────────────────────────────────

export function useHealth(intervalMs = 5000) {
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    const fetchHealth = () => {
      orionApi.health().then(setHealth).catch(() => setHealth(null));
    };
    fetchHealth();
    const id = setInterval(fetchHealth, intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);

  return health;
}

// ── useTasks ─────────────────────────────────────────────────────

export function useTasks(intervalMs = 2000) {
  const [tasks, setTasks] = useState<Task[]>([]);

  const refetch = useCallback(() => {
    orionApi.getTasks().then(setTasks).catch(() => {});
  }, []);

  useEffect(() => {
    refetch();
    const id = setInterval(refetch, intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, refetch]);

  return { tasks, refetch };
}

// ── useTaskEvents ────────────────────────────────────────────────

export function useTaskEvents(taskId: string | null) {
  const [events, setEvents] = useState<RuntimeEvent[]>([]);

  useEffect(() => {
    if (!taskId) {
      setEvents([]);
      return;
    }
    orionApi.getTaskEvents(taskId).then(setEvents).catch(() => setEvents([]));
  }, [taskId]);

  return events;
}

// ── useConversations ─────────────────────────────────────────────

export function useConversations(intervalMs = 3000) {
  const [messages, setMessages] = useState<ConversationMessage[]>([]);

  useEffect(() => {
    const fetchConversations = () => {
      orionApi.getConversations().then(setMessages).catch(() => {});
    };
    fetchConversations();
    const id = setInterval(fetchConversations, intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);

  return messages;
}

// ── useToast ─────────────────────────────────────────────────────

interface Toast {
  id: number;
  message: string;
  type: "success" | "error" | "info";
}

export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counterRef = useRef(0);

  const addToast = useCallback(
    (message: string, type: "success" | "error" | "info" = "info") => {
      const id = ++counterRef.current;
      setToasts((prev) => [...prev, { id, message, type }]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 4000);
    },
    []
  );

  return { toasts, addToast };
}
