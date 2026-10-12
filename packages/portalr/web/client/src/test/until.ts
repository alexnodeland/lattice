/** Waits until a store's snapshot satisfies a condition, or fails after a few seconds. */

interface Store<S> {
  snapshot(): S;
  subscribe(listener: () => void): () => void;
}

export function until<S>(store: Store<S>, condition: (snapshot: S) => boolean): Promise<S> {
  return new Promise((resolve, reject) => {
    const check = () => {
      if (condition(store.snapshot())) {
        unsubscribe();
        clearTimeout(timer);
        resolve(store.snapshot());
      }
    };
    const unsubscribe = store.subscribe(check);
    const timer = setTimeout(() => {
      unsubscribe();
      reject(new Error(`timed out at ${JSON.stringify(store.snapshot())}`));
    }, 5000);
    check();
  });
}
