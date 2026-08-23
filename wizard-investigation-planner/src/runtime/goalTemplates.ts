/**
 * Goal templates — turn a TechnologyPlanItem's named goals (e.g. "Verify
 * Runtime") into concrete `Goal` objects with machine-checkable requirements.
 *
 * Keeping this as a small deterministic table (rather than asking the LLM) means
 * goal semantics are auditable and stable: "Verify Runtime" always means the
 * same claim requirements. The Planner chooses WHICH goals apply; this table
 * defines what each goal REQUIRES.
 */
import type { Goal, GoalRequirement } from "../core/types.ts";
import type { IdFactory } from "../util/ids.ts";

type RequirementTemplate = Omit<GoalRequirement, "description"> & { description: string };

const GOAL_REQUIREMENTS: Record<string, RequirementTemplate[]> = {
  "Verify Runtime": [
    {
      claimType: "RUNTIME_STATUS",
      notValue: "broken",
      minTrust: 0.6,
      description: "The runtime can be verified as working (not broken)",
    },
  ],
  "Verify Dependencies": [
    {
      claimType: "MANIFEST_PARSED",
      minTrust: 0.5,
      description: "A dependency manifest was located and parsed",
    },
  ],
  "Verify Containerization": [
    {
      claimType: "MANIFEST_PARSED",
      minTrust: 0.5,
      description: "A Dockerfile / compose file was located and parsed",
    },
  ],
};

/** Fallback for an unknown goal name: require a single positive claim by name. */
function fallbackRequirements(goalName: string): RequirementTemplate[] {
  return [
    {
      claimType: goalName.toUpperCase().replace(/[^A-Z0-9]+/g, "_"),
      minTrust: 0.5,
      description: `Evidence gathered for "${goalName}"`,
    },
  ];
}

export function buildGoal(
  goalName: string,
  technology: string,
  ids: IdFactory,
): Goal {
  const reqs = GOAL_REQUIREMENTS[goalName] ?? fallbackRequirements(goalName);
  return {
    goalId: ids.next("goal"),
    name: goalName,
    technology,
    status: "waiting",
    requirements: reqs.map((r) => ({ ...r })),
  };
}
