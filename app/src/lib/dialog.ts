import { open, save } from "@tauri-apps/plugin-dialog";

export interface FileFilter {
  name: string;
  extensions: string[];
}

export const pickFile = async (
  filters?: FileFilter[],
): Promise<string | null> => {
  const r = await open({ multiple: false, filters });
  return typeof r === "string" ? r : null;
};

export const pickFiles = async (
  filters?: FileFilter[],
): Promise<string[] | null> => {
  const r = await open({ multiple: true, filters });
  return Array.isArray(r) ? r : r ? [r] : null;
};

export const pickFolder = async (): Promise<string | null> => {
  const r = await open({ directory: true });
  return typeof r === "string" ? r : null;
};

export const pickSave = async (
  defaultPath: string,
  filters?: FileFilter[],
): Promise<string | null> => {
  const r = await save({ defaultPath, filters });
  return typeof r === "string" ? r : null;
};
