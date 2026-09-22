"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { describeError } from "./api";

interface State<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/** Basit veri çekme kancası: yükleme, hata ve yeniden deneme. */
export function useApi<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: true });
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const reload = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const data = await loaderRef.current();
      setState({ data, error: null, loading: false });
    } catch (error) {
      setState((prev) => ({ data: prev.data, error: describeError(error), loading: false }));
    }
  }, []);

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { ...state, reload, setData: (data: T) => setState({ data, error: null, loading: false }) };
}
