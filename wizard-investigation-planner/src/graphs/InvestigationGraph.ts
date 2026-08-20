/**
 * Investigation Graph — GRAPH 2 of the two-graph architecture.
 *
 * Answers: "HOW are we getting there?" It is a directed graph of Investigation
 * Nodes (units of work). It grows dynamically as the Planner proposes nodes and
 * the Runtime materialises them.
 *
 * It stores ONLY Investigation Nodes and their edges. It NEVER stores Claims.
 * (Claims live in the Knowledge Graph.) This separation is enforced by type:
 * this class only accepts `InvestigationNode`.
 */
import type {
  InvestigationEdge,
  InvestigationGraphSnapshot,
  InvestigationNode,
  NodeId,
  NodeStatus,
} from "../core/types.ts";

export class InvestigationGraph {
  private readonly nodes = new Map<NodeId, InvestigationNode>();
  private readonly order: NodeId[] = [];

  addNode(node: InvestigationNode): void {
    if (this.nodes.has(node.nodeId)) {
      throw new Error(`Duplicate node id in Investigation Graph: ${node.nodeId}`);
    }
    this.nodes.set(node.nodeId, node);
    this.order.push(node.nodeId);
  }

  hasNode(nodeId: NodeId): boolean {
    return this.nodes.has(nodeId);
  }

  getNode(nodeId: NodeId): InvestigationNode | undefined {
    return this.nodes.get(nodeId);
  }

  requireNode(nodeId: NodeId): InvestigationNode {
    const n = this.nodes.get(nodeId);
    if (!n) throw new Error(`Investigation node not found: ${nodeId}`);
    return n;
  }

  allNodes(): InvestigationNode[] {
    return this.order.map((id) => this.nodes.get(id)!).filter(Boolean);
  }

  nodesByStatus(status: NodeStatus): InvestigationNode[] {
    return this.allNodes().filter((n) => n.status === status);
  }

  childrenOf(nodeId: NodeId): InvestigationNode[] {
    return this.allNodes().filter((n) => n.parentNodeId === nodeId);
  }

  /** update a node in place (Runtime-owned mutation of status/observation/etc). */
  updateNode(nodeId: NodeId, patch: Partial<InvestigationNode>): InvestigationNode {
    const node = this.requireNode(nodeId);
    const updated: InvestigationNode = { ...node, ...patch, nodeId: node.nodeId };
    this.nodes.set(nodeId, updated);
    return updated;
  }

  /** Are all dependency nodes complete? */
  dependenciesSatisfied(nodeId: NodeId): boolean {
    const node = this.requireNode(nodeId);
    return node.dependencies.every((dep) => this.nodes.get(dep)?.status === "complete");
  }

  /** Does any dependency of this node exist but has failed/been skipped? */
  hasBlockedDependency(nodeId: NodeId): boolean {
    const node = this.requireNode(nodeId);
    return node.dependencies.some((dep) => {
      const d = this.nodes.get(dep);
      return d !== undefined && (d.status === "failed" || d.status === "skipped");
    });
  }

  edges(): InvestigationEdge[] {
    const edges: InvestigationEdge[] = [];
    for (const node of this.allNodes()) {
      if (node.parentNodeId && this.nodes.has(node.parentNodeId)) {
        edges.push({ from: node.parentNodeId, to: node.nodeId, type: "parent" });
      }
      for (const dep of node.dependencies) {
        if (this.nodes.has(dep)) edges.push({ from: dep, to: node.nodeId, type: "dependency" });
      }
    }
    return edges;
  }

  /**
   * Detect a dependency cycle reachable from `startId` (used before inserting a
   * node whose dependencies could introduce a cycle). Returns the cycle path if
   * found, else null.
   */
  findDependencyCycle(): NodeId[] | null {
    const WHITE = 0;
    const GRAY = 1;
    const BLACK = 2;
    const color = new Map<NodeId, number>();
    const stack: NodeId[] = [];

    const visit = (id: NodeId): NodeId[] | null => {
      color.set(id, GRAY);
      stack.push(id);
      const node = this.nodes.get(id);
      if (node) {
        for (const dep of node.dependencies) {
          if (!this.nodes.has(dep)) continue;
          const c = color.get(dep) ?? WHITE;
          if (c === GRAY) {
            const idx = stack.indexOf(dep);
            return stack.slice(idx).concat(dep);
          }
          if (c === WHITE) {
            const found = visit(dep);
            if (found) return found;
          }
        }
      }
      stack.pop();
      color.set(id, BLACK);
      return null;
    };

    for (const id of this.order) {
      if ((color.get(id) ?? WHITE) === WHITE) {
        const cycle = visit(id);
        if (cycle) return cycle;
      }
    }
    return null;
  }

  snapshot(): InvestigationGraphSnapshot {
    return { nodes: this.allNodes(), edges: this.edges() };
  }

  size(): number {
    return this.nodes.size;
  }

  /**
   * ASCII tree rendering rooted at nodes with no parent. Dependencies are shown
   * inline as "[after: node_x]". Used by the report and CLI to make the
   * investigation path human-inspectable.
   */
  render(): string {
    const roots = this.allNodes().filter((n) => !n.parentNodeId || !this.nodes.has(n.parentNodeId));
    const lines: string[] = [];
    const seen = new Set<NodeId>();

    const label = (n: InvestigationNode): string => {
      const status = `[${n.status}]`;
      const deps = n.dependencies.length ? ` (after: ${n.dependencies.join(", ")})` : "";
      const claim =
        n.status === "complete" && n.successClaim
          ? ` -> ${n.successClaim.type}=${n.successClaim.value}`
          : "";
      return `${n.nodeId} ${n.type}: ${describeAction(n)} ${status}${deps}${claim}`;
    };

    const walk = (n: InvestigationNode, prefix: string, isLast: boolean): void => {
      if (seen.has(n.nodeId)) return;
      seen.add(n.nodeId);
      const connector = prefix === "" ? "" : isLast ? "└── " : "├── ";
      lines.push(`${prefix}${connector}${label(n)}`);
      const children = this.childrenOf(n.nodeId);
      const childPrefix = prefix === "" ? "" : prefix + (isLast ? "    " : "│   ");
      children.forEach((child, i) => walk(child, childPrefix, i === children.length - 1));
    };

    roots.forEach((r, i) => walk(r, "", i === roots.length - 1));
    // any orphans not reached
    for (const n of this.allNodes()) {
      if (!seen.has(n.nodeId)) lines.push(label(n));
    }
    return lines.join("\n");
  }
}

function describeAction(n: InvestigationNode): string {
  const a = n.action;
  switch (a.type) {
    case "discovery":
      return `discover "${a.pattern}"`;
    case "read":
      return a.filePath;
    case "execute":
      return `\`${a.command}\``;
    case "parse":
      return `parse(${a.parser})`;
    case "verify":
      return `verify`;
    case "synthesize":
      return `synthesize`;
    case "planner":
      return `plan (${a.reason})`;
    case "checkpoint":
      return `checkpoint ${a.goalId}`;
    default:
      return "";
  }
}
