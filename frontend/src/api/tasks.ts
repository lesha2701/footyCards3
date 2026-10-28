import { api } from "@/lib/api";
import type { TaskChestClaimResult, TaskClaimResult, TaskList, TaskRerollResult } from "@/types";

export async function fetchTasks(): Promise<TaskList> {
  const { data } = await api.get<TaskList>("/tasks");
  return data;
}

export async function claimTask(userTaskId: number): Promise<TaskClaimResult> {
  const { data } = await api.post<TaskClaimResult>(`/tasks/${userTaskId}/claim`);
  return data;
}

export async function claimTaskChest(period: "daily" | "weekly", index: number): Promise<TaskChestClaimResult> {
  const { data } = await api.post<TaskChestClaimResult>(`/tasks/chests/${period}/${index}/claim`);
  return data;
}

export async function rerollTask(userTaskId: number): Promise<TaskRerollResult> {
  const { data } = await api.post<TaskRerollResult>(`/tasks/${userTaskId}/reroll`);
  return data;
}
