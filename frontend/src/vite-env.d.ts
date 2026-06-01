/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend origin for packaged builds, e.g. http://192.168.0.94:8000. Empty in dev. */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
