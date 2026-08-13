import React, { act } from "react";
import { createRoot } from "react-dom/client";

import AcademicScopeNavigator from "./AcademicScopeNavigator";

const hierarchy = {
  items: [{
    graduation_year: 2027,
    label: "Class of 2027",
    student_count: 40,
    placed_count: 18,
    unplaced_count: 22,
    department_count: 1,
    section_count: 2,
    departments: [{
      id: "department-cse",
      name: "Computer Science and Engineering",
      code: "CSE",
      student_count: 40,
      placed_count: 18,
      unplaced_count: 22,
      section_count: 2,
      programs: [{
        id: "program-cse",
        name: "B.E. Computer Science",
        code: "BE-CSE",
        student_count: 40,
        placed_count: 18,
        unplaced_count: 22,
        section_count: 2,
        sections: [
          { id: "cse-a", name: "CSE A", section: "A", current_semester: 7, student_count: 20, placed_count: 10, unplaced_count: 10 },
          { id: "cse-b", name: "CSE B", section: "B", current_semester: 7, student_count: 20, placed_count: 8, unplaced_count: 12 },
        ],
      }],
    }],
  }],
};

async function renderNavigator(value, onChange = vi.fn()) {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<AcademicScopeNavigator data={hierarchy} value={value} onChange={onChange} />);
  });
  return {
    container,
    onChange,
    cleanup: () => {
      act(() => root.unmount());
      container.remove();
      delete global.IS_REACT_ACT_ENVIRONMENT;
    },
  };
}

test("drills from graduation batch into department and section cards", async () => {
  const view = await renderNavigator({ graduationYear: 2027, departmentId: "department-cse", cohortId: null });
  expect(view.container.textContent).toContain("Class of 2027");
  expect(view.container.textContent).toContain("Computer Science and Engineering");
  expect(view.container.textContent).toContain("CSE A");
  expect(view.container.textContent).toContain("CSE B");
  expect(view.container.textContent).toContain("10 placed");
  view.cleanup();
});

test("emits a scoped selection without mutating unrelated filters", async () => {
  const view = await renderNavigator({ graduationYear: null, departmentId: null, cohortId: null });
  const batchButton = [...view.container.querySelectorAll("button")].find((button) => button.textContent.includes("Class of 2027"));
  await act(async () => batchButton.click());
  expect(view.onChange).toHaveBeenCalledWith({ graduationYear: 2027, departmentId: null, cohortId: null });
  view.cleanup();
});
