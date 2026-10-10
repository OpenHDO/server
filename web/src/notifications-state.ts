export type Notice = {
  id: number;
  tone: "error" | "success";
  message: string;
  action?: { label: string; onClick: () => void };
};

export function addNotice(current: Notice[], notice: Notice) {
  if (
    current.some(
      (item) => item.tone === notice.tone && item.message === notice.message,
    )
  )
    return current;
  return [...current, notice].slice(-3);
}
