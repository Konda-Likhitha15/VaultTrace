/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DOCUMENT_MAX_UPLOAD_BYTES?: string;
  readonly VITE_DOCUMENT_ALLOWED_EXTENSIONS?: string;
  readonly VITE_API_BASE_URL?: string;
}
