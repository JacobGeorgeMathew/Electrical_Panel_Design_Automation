// src/api/config.ts
export const API_BASE =
  import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8731/api";

//On Create React App, use process.env.REACT_APP_API_BASE instead of import.meta.env.VITE_API_BASE.
