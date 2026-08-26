"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"

type FileNode = { name: string; type: "file" | "folder"; children?: FileNode[]; extension?: string }

const iconFor = (extension?: string) => ({
  tsx: ["◆", "text-sky-400"], ts: ["◆", "text-blue-400"], json: ["{}", "text-amber-300"], css: ["◈", "text-violet-400"], md: ["◊", "text-slate-400"],
}[extension || ""] || ["◇", "text-slate-500"]) as [string, string]

function FileItem({ node, depth }: { node: FileNode; depth: number }) {
  const [open, setOpen] = useState(true)
  const folder = node.type === "folder"
  const [icon, color] = iconFor(node.extension)
  return <div className="select-none">
    <button type="button" className="file-tree-item group" style={{ paddingLeft: depth * 14 + 8 }} onClick={() => folder && setOpen(!open)}>
      <span className={cn("file-tree-chevron", folder && open && "rotate-90")}>{folder ? "›" : icon}</span>
      <span className={cn("file-tree-icon", folder ? "text-blue-400" : color)}>{folder ? "▰" : "▱"}</span>
      <span className={cn("truncate", folder ? "text-slate-200" : "text-slate-400")}>{node.name}</span>
      <span className="file-tree-active-dot" />
    </button>
    {folder && open && node.children?.map(child => <FileItem key={child.name} node={child} depth={depth + 1} />)}
  </div>
}

export function FileTree({ data, className }: { data: FileNode[]; className?: string }) {
  return <div className={cn("file-tree-panel", className)}>
    <div className="file-tree-header"><span className="traffic red" /><span className="traffic yellow" /><span className="traffic green" /><span>EXPLORER</span><span className="ml-auto">WIZARD REPO</span></div>
    <div className="file-tree-content">{data.map(node => <FileItem key={node.name} node={node} depth={0} />)}</div>
  </div>
}

export const wizardFileStructure: FileNode[] = [
  { name: "app", type: "folder", children: [{ name: "page.tsx", type: "file", extension: "tsx" }, { name: "layout.tsx", type: "file", extension: "tsx" }] },
  { name: "components", type: "folder", children: [{ name: "hero.tsx", type: "file", extension: "tsx" }, { name: "file-tree.tsx", type: "file", extension: "tsx" }] },
  { name: "lib", type: "folder", children: [{ name: "utils.ts", type: "file", extension: "ts" }] },
  { name: "package.json", type: "file", extension: "json" },
  { name: "globals.css", type: "file", extension: "css" },
]
