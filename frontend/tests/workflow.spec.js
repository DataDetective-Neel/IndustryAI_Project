import { test, expect } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { execFileSync } from "node:child_process";

const root = path.resolve("..");
const python = path.join(root, ".venv/Scripts/python.exe");
const names = [
  "upper_left_mount",
  "upper_right_mount",
  "lower_right_mount",
  "lower_left_mount",
];
const absolute = (name) => path.join(root, name);
const readJson = async (name) =>
  JSON.parse(await fs.readFile(absolute(name), "utf8"));

test("a rejected upload does not discard the other selected photo", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByLabel("Reference photo", { exact: true })
    .setInputFiles(absolute("PCB_Dataset_Pilot/images/val/ECCC5.jpg"));
  await expect(
    page.getByRole("button", { name: "Add box", exact: true }),
  ).toBeEnabled();
  await page.route("**/api/photos", (route) => {
    if (route.request().postData()?.includes("too-large.png"))
      return route.fulfill({
        status: 413,
        json: { detail: "Photo exceeds 12 MiB upload limit" },
      });
    return route.continue();
  });
  await page.getByLabel("Inspection photos", { exact: true }).setInputFiles([
    {
      name: "too-large.png",
      mimeType: "image/png",
      buffer: Buffer.from("simulated rejection"),
    },
    {
      name: "valid.png",
      mimeType: "image/png",
      buffer: await fs.readFile(
        absolute("PCB_Dataset_Pilot/images/val/ECCB5.jpg"),
      ),
    },
  ]);
  await expect(page.getByRole("alert")).toContainText(
    "too-large.png: Photo exceeds 12 MiB",
  );
  await expect(
    page.getByRole("button", { name: /Inspection 1 valid.png/ }),
  ).toBeVisible();
});
async function pointsFromLabel(label, width, height) {
  const values = (await fs.readFile(absolute(label), "utf8"))
    .trim()
    .split(/\s+/)
    .map(Number);
  return names.map((_, i) => [
    values[5 + i * 3] * width,
    values[6 + i * 3] * height,
  ]);
}
async function mark(page, points) {
  for (let i = 0; i < 4; i++)
    for (const [axis, j] of [
      ["x", 0],
      ["y", 1],
    ])
      await page
        .getByLabel(`${names[i]} ${axis}`, { exact: true })
        .fill(String(points[i][j]));
}
async function region(page, part) {
  await page.getByRole("button", { name: "Add box", exact: true }).click();
  await page.getByLabel("Component name", { exact: true }).fill(part.name);
  for (let i = 0; i < 4; i++)
    await page
      .getByLabel(`Region ${["x1", "y1", "x2", "y2"][i]}`, { exact: true })
      .fill(String(part.bbox_xyxy_px[i]));
  if (part.review_reason) {
    await page.getByLabel("Flag region for review").check();
    await page
      .getByLabel("Review reason", { exact: true })
      .fill(part.review_reason);
  }
}
async function inspect(page) {
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/inspections") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: /^Inspect \d+ photo/ }).click();
  const result = await (await response).json();
  await expect(
    page.getByRole("heading", { name: "Inspection results", exact: true }),
  ).toBeVisible();
  return result;
}

test("real manual workflow matches CLI; edit/remove, resize, automatic rejection and sibling isolation", async ({
  page,
}) => {
  const external = [],
    errors = [];
  page.on("request", (request) => {
    if (!["127.0.0.1", "localhost"].includes(new URL(request.url()).hostname))
      external.push(request.url());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page
    .getByLabel("Reference photo", { exact: true })
    .setInputFiles(absolute("PCB_Dataset_Pilot/images/val/ECCC5.jpg"));
  await expect(
    page.getByRole("button", { name: "Add box", exact: true }),
  ).toBeEnabled();
  await mark(
    page,
    await pointsFromLabel("PCB_Dataset_Pilot/labels/val/ECCC5.txt", 1174, 1536),
  );
  await page
    .getByRole("button", { name: "Draw part boxes", exact: true })
    .click();
  const canvas = page.locator("svg.photo-canvas");
  await canvas.scrollIntoViewIfNeeded();
  let rect = await canvas.boundingBox();
  await page.mouse.move(rect.x + rect.width * 0.2, rect.y + rect.height * 0.2);
  await page.mouse.down();
  await page.mouse.move(
    rect.x + rect.width * 0.35,
    rect.y + rect.height * 0.35,
  );
  await page.mouse.up();
  await page
    .getByLabel("Component name", { exact: true })
    .fill("Draw/edit/remove check");
  await expect(
    page.getByRole("button", { name: "Draw/edit/remove check", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Remove component", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Draw/edit/remove check", exact: true }),
  ).toHaveCount(0);
  const parts = (await readJson("configs/components-ECCC5.json")).components;
  // The exact known-good reference loads its eight saved regions automatically.
  await page.getByRole("button", {name: parts.at(-1).name, exact:true}).click();
  const before = await page
    .getByLabel("upper_left_mount x", { exact: true })
    .inputValue();
  const beforeBox = await Promise.all(
    ["x1", "y1", "x2", "y2"].map((axis) =>
      page.getByLabel(`Region ${axis}`, { exact: true }).inputValue(),
    ),
  );
  await page.getByLabel("Preview width", { exact: true }).fill("400");
  await page.setViewportSize({ width: 1000, height: 1000 });
  await expect(
    page.getByLabel("upper_left_mount x", { exact: true }),
  ).toHaveValue(before);
  expect(
    await Promise.all(
      ["x1", "y1", "x2", "y2"].map((axis) =>
        page.getByLabel(`Region ${axis}`, { exact: true }).inputValue(),
      ),
    ),
  ).toEqual(beforeBox);
  await page
    .getByRole("button", { name: "Draw part boxes", exact: true })
    .click();
  await canvas.scrollIntoViewIfNeeded();
  rect = await canvas.boundingBox();
  await page.mouse.move(rect.x + rect.width * 0.1, rect.y + rect.height * 0.1);
  await page.mouse.down();
  await page.mouse.move(rect.x + rect.width * 0.2, rect.y + rect.height * 0.2);
  await page.mouse.up();
  const resizedBox = await Promise.all(
    ["x1", "y1", "x2", "y2"].map(async (axis) =>
      Number(
        await page.getByLabel(`Region ${axis}`, { exact: true }).inputValue(),
      ),
    ),
  );
  resizedBox.forEach((value, i) =>
    expect(Math.abs(value - [117, 153, 235, 308][i])).toBeLessThanOrEqual(3),
  );
  await page
    .getByRole("button", { name: "Remove component", exact: true })
    .click();
  // Place a point using a resized canvas, then restore the exact reviewed value.
  await page
    .getByRole("button", { name: "L0 upper_left_mount", exact: true })
    .click();
  await canvas.scrollIntoViewIfNeeded();
  rect = await canvas.boundingBox();
  await page.mouse.click(rect.x + rect.width * 0.1, rect.y + rect.height * 0.1);
  expect(
    Number(
      await page.getByLabel("upper_left_mount x", { exact: true }).inputValue(),
    ),
  ).toBeCloseTo(117.4, 0);
  expect(
    Number(
      await page.getByLabel("upper_left_mount y", { exact: true }).inputValue(),
    ),
  ).toBeCloseTo(153.6, 0);
  await mark(
    page,
    await pointsFromLabel("PCB_Dataset_Pilot/labels/val/ECCC5.txt", 1174, 1536),
  );
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page
    .getByLabel("Inspection photos", { exact: true })
    .setInputFiles(absolute("PCB_Dataset_Pilot/images/val/ECCB5.jpg"));
  await expect(
    page.getByRole("button", { name: /Inspection 1 ECCB5.jpg/ }),
  ).toBeVisible();
  await mark(
    page,
    await pointsFromLabel("PCB_Dataset_Pilot/labels/val/ECCB5.txt", 1162, 1536),
  );
  const manual = await inspect(page);
  expect(manual.photos[0].components).toHaveLength(8);
  expect(manual.photos[0].components.some((p) => p.status === "missing")).toBe(false);
  // Run the actual Step 5 CLI with matching frozen settings into a fresh local directory.
  const cliDir = absolute(`runs/web-verification/cli-${manual.batch_id}`);
  const alignmentDir = absolute(
    `runs/web-verification/align-${manual.batch_id}`,
  );
  execFileSync(
    python,
    [
      "-m",
      "pcb_landmarks.align",
      "--reference",
      "PCB_Dataset_Pilot/images/val/ECCC5.jpg",
      "--inspection",
      "PCB_Dataset_Pilot/images/val/ECCB5.jpg",
      "--reference-label",
      "PCB_Dataset_Pilot/labels/val/ECCC5.txt",
      "--inspection-label",
      "PCB_Dataset_Pilot/labels/val/ECCB5.txt",
      "--output",
      alignmentDir,
    ],
    { cwd: root },
  );
  execFileSync(
    python,
    [
      "-m",
      "pcb_landmarks.compare",
      "--reference",
      "PCB_Dataset_Pilot/images/val/ECCC5.jpg",
      "--aligned",
      path.join(alignmentDir, "aligned.png"),
      "--mask",
      path.join(alignmentDir, "overlap_mask.png"),
      "--regions",
      "configs/components-ECCC5.json",
      "--output",
      cliDir,
    ],
    { cwd: root },
  );
  const cli = JSON.parse(
    await fs.readFile(path.join(cliDir, "report.json"), "utf8"),
  );
  manual.photos[0].components.forEach((p, i) => {
    expect(p.status).toBe(cli.components[i].status);
    expect(p.score).toBe(cli.components[i].score);
  });
  await expect(
    page
      .getByTestId("result-0")
      .getByRole("cell", { name: "Present", exact: true }),
  ).toHaveCount(manual.photos[0].components.filter((p) => p.status === "present").length);
  await page.screenshot({
    path: absolute("runs/web-verification/real-manual.png"),
    fullPage: true,
  });
  await page.getByRole("radio", { name: "Automatic", exact: true }).check();
  await expect(
    page.getByText("Detecting landmarks with the local model…"),
  ).toHaveCount(0, { timeout: 60000 });
  const automatic = await inspect(page);
  expect(automatic.photos[0].outcome).toBe("review");
  expect(automatic.photos[0].alignment.reason).toMatch(
    /no_confident_board|low_landmark_confidence|checkpoint_unavailable/,
  );
  await expect(
    page
      .getByTestId("result-0")
      .getByText("Component scoring skipped.", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: absolute("runs/web-verification/automatic-rejection.png"),
    fullPage: true,
  });
  await page
    .getByTestId("result-0")
    .getByRole("button", { name: "Switch to Manual", exact: true })
    .click();
  await page.getByLabel("Inspection photos", { exact: true }).setInputFiles({
    name: "broken.png",
    mimeType: "image/png",
    buffer: Buffer.from("not an image"),
  });
  await expect(
    page.getByText("Photo needs review:", { exact: false }),
  ).toBeVisible();
  const mixed = await inspect(page);
  expect(mixed.photos.map((p) => p.outcome)).toEqual(["review", "error"]);
  await expect(
    page
      .getByTestId("result-0")
      .getByRole("img", { name: /Component decisions/ }),
  ).toBeVisible();
  await expect(
    page
      .getByTestId("result-1")
      .getByText("Component scoring skipped.", { exact: true }),
  ).toBeVisible();
  expect(external).toEqual([]);
  expect(errors).toEqual([]);
  await fs.writeFile(
    absolute("runs/web-verification/browser-real.json"),
    JSON.stringify({ manual, automatic, mixed }, null, 2),
  );
});

for (const [variant, url] of [
  ["Vite", "/"],
  ["production", "http://127.0.0.1:8000/"],
])
  test(`synthetic removal requires review, sharpening and local-only assets (${variant})`, async ({
    page,
  }) => {
    const external = [];
    await page.route("**/*", (route) => {
      const host = new URL(route.request().url()).hostname;
      if (!["127.0.0.1", "localhost"].includes(host)) {
        external.push(route.request().url());
        return route.abort();
      }
      return route.continue();
    });
    const example = absolute("runs/comparison/synthetic-input");
    try {
      await fs.access(example);
    } catch {
      execFileSync(
        python,
        ["tests/comparison_fixture.py", "--output", example],
        { cwd: root },
      );
    }
    await page.goto(url);
    await page
      .getByLabel("Reference photo", { exact: true })
      .setInputFiles(path.join(example, "input/reference.png"));
    await expect(
      page.getByRole("button", { name: "Add box", exact: true }),
    ).toBeEnabled();
    await mark(
      page,
      await pointsFromLabel(
        "runs/comparison/synthetic-input/input/reference.txt",
        320,
        240,
      ),
    );
    const parts = JSON.parse(
      await fs.readFile(path.join(example, "regions.json"), "utf8"),
    ).components;
    for (const part of parts) await region(page, part);
    await page
      .getByLabel("Inspection photos", { exact: true })
      .setInputFiles(path.join(example, "input/inspection.png"));
    await expect(
      page.getByRole("button", { name: /Inspection 1 inspection.png/ }),
    ).toBeVisible();
    await mark(
      page,
      await pointsFromLabel(
        "runs/comparison/synthetic-input/input/inspection.txt",
        300,
        280,
      ),
    );
    await page
      .getByLabel("Label this run as a synthetic demonstration")
      .check();
    const result = await inspect(page);
    expect(result.synthetic).toBe(true);
    expect(result.photos[0].components.map((p) => p.status)).toEqual([
      "present",
      "uncertain",
      "uncertain",
    ]);
    await expect(
      page.getByText(
        "Synthetic demonstration — controlled image example, not a real defective board.",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(
      page
        .getByTestId("result-0")
        .getByRole("cell", { name: "Needs review", exact: true }),
    ).toHaveCount(2);
    await page.screenshot({
      path: absolute("runs/web-verification/synthetic-missing.png"),
      fullPage: true,
    });
    await fs.writeFile(
      absolute("runs/web-verification/browser-synthetic.json"),
      JSON.stringify(result, null, 2),
    );
    await page.getByLabel("Optional sharpening", { exact: true }).check();
    const sharpened = await inspect(page);
    expect(sharpened.sharpening_enabled).toBe(true);
    expect(sharpened.photos[0].components.map((p) => p.status)).toEqual([
      "present",
      "uncertain",
      "uncertain",
    ]);
    expect(sharpened.photos[0].components[1].reason).toContain("low similarity alone");
    expect(external).toEqual([]);
    await fs.writeFile(
      absolute("runs/web-verification/browser-synthetic-sharpen.json"),
      JSON.stringify(sharpened, null, 2),
    );
    await page.setViewportSize({ width: 375, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: absolute(`runs/web-verification/mobile-${variant}.png`),
      fullPage: true,
    });
  });
