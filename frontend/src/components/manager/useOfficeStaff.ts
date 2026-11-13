import { useQuery } from "@tanstack/react-query";

import { fetchManagerAssistant, fetchManagerStaff } from "@/api/manager";

/** The worn office items and the assistant's line for the hero. */
export function useOfficeStaff() {
  const staff = useQuery({ queryKey: ["manager", "staff"], queryFn: fetchManagerStaff, staleTime: 60_000 });
  const assistant = useQuery({ queryKey: ["manager", "assistant"], queryFn: fetchManagerAssistant, staleTime: 30_000 });
  return { staff: staff.data, assistant: assistant.data };
}
