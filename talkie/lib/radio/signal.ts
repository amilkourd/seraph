import type { Unsubscribe } from "./types";

/** A value with subscribers. `subscribe` replays the current value, which is what every `on*` method promises. */
export class Signal<T> {
  private subs = new Set<(v: T) => void>();
  constructor(private value: T) {}

  get(): T {
    return this.value;
  }

  set(v: T): void {
    if (Object.is(v, this.value)) return;
    this.value = v;
    for (const cb of [...this.subs]) cb(v);
  }

  subscribe(cb: (v: T) => void): Unsubscribe {
    this.subs.add(cb);
    cb(this.value);
    return () => this.subs.delete(cb);
  }
}
