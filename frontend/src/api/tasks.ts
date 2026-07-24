import { api } from "@/lib/api";
import type { TaskClaimResult, TaskList } from "@/types";

export async function fetchTasks(): Promise<TaskList> {
  const { data } = await api.get<TaskList>("/tasks");
  return data;
}

export async function claimTask(userTaskId: number): Promise<TaskClaimResult> {
  const { data } = await api.post<TaskClaimResult>(`/tasks/${userTaskId}/claim`);
  return data;
}
