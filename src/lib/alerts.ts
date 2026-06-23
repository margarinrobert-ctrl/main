export interface NamedLevel {
  name: string;
  value: number | null;
}

const key = (sym: string) => `alerts:${sym.toUpperCase()}`;

export function alertsEnabled(sym: string): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(key(sym)) === "1";
}

export function setAlertsEnabled(sym: string, on: boolean): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(key(sym), on ? "1" : "0");
  } catch {
    /* ignore */
  }
}

export async function requestNotifyPermission(): Promise<boolean> {
  if (typeof window === "undefined" || !("Notification" in window)) return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") return false;
  try {
    return (await Notification.requestPermission()) === "granted";
  } catch {
    return false;
  }
}

export function fireNotify(title: string, body: string): void {
  try {
    if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
      new Notification(title, { body });
    }
  } catch {
    /* ignore */
  }
}

/** Levels whose value lies between prev and now (i.e. price crossed them). */
export function crossings(prev: number | null, now: number | null, levels: NamedLevel[]): NamedLevel[] {
  if (prev == null || now == null || prev === now) return [];
  return levels.filter(
    (l) => l.value != null && ((prev < l.value && now >= l.value) || (prev > l.value && now <= l.value)),
  );
}
