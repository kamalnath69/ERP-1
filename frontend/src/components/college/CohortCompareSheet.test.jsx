import React, { act } from "react";
import { createRoot } from "react-dom/client";

import CohortCompareSheet from "./CohortCompareSheet";

const hierarchy = {
  items: [
    {
      graduation_year: 2026,
      label: "Class of 2026",
      departments: [{
        id: "dept-aiml",
        name: "Artificial Intelligence and Machine Learning",
        code: "AIML",
        programs: [{
          id: "program-aiml",
          name: "B.Tech Artificial Intelligence",
          code: "BTECH-AIML",
          sections: [{ id: "aiml-2026-a", name: "AIML A", code: "AIML-2026-A", section: "A", student_count: 28 }],
        }],
      }],
    },
    {
      graduation_year: 2027,
      label: "Class of 2027",
      departments: [{
        id: "dept-eee",
        name: "Electrical and Electronics Engineering",
        code: "EEE",
        programs: [{
          id: "program-eee",
          name: "B.E. Electrical and Electronics Engineering",
          code: "BE-EEE",
          sections: [{ id: "eee-2027-general", name: "EEE 2027", code: "EEE-2027", section: "GENERAL", student_count: 31 }],
        }],
      }],
    },
  ],
};

async function renderCompare(selectedIds, onApply = vi.fn()) {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<CohortCompareSheet data={hierarchy} selectedIds={selectedIds} onApply={onApply} />);
  });
  return {
    container,
    onApply,
    cleanup: () => {
      act(() => root.unmount());
      container.remove();
      delete global.IS_REACT_ACT_ENVIRONMENT;
    },
  };
}

test("shows selected cohorts from different graduation years and removes one scope", async () => {
  const view = await renderCompare(["aiml-2026-a", "eee-2027-general"]);
  expect(view.container.textContent).toContain("AIML / BTECH-AIML / A / 2026");
  expect(view.container.textContent).toContain("EEE / BE-EEE / GENERAL / 2027");

  const aimlChip = [...view.container.querySelectorAll("button")]
    .find((button) => button.textContent.includes("AIML / BTECH-AIML"));
  await act(async () => aimlChip.click());
  expect(view.onApply).toHaveBeenCalledWith(["eee-2027-general"]);
  view.cleanup();
});

