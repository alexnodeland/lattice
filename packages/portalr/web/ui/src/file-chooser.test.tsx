import { expect, onTestFinished, test } from "vitest";
import { commands, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { FileChooser } from "./file-chooser";
import { Progress } from "./progress";
import { axeViolations } from "./test/axe";
import { token } from "./test/colours";

/** Drop files on an element, as a drag from the desktop would. */
function drop(on: Element, ...files: File[]) {
  const data = new DataTransfer();
  for (const file of files) {
    data.items.add(file);
  }
  for (const type of ["dragenter", "dragover", "drop"]) {
    on.dispatchEvent(new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer: data }));
  }
}

test("a file is chosen through its labelled input, described with how else to give it", async () => {
  const chosen: string[] = [];
  const screen = await render(
    <FileChooser
      label="The edited file"
      hint="The file you saved, up to 25 MB."
      accept=".docx"
      onFile={(file) => chosen.push(file.name)}
    />,
  );
  const input = screen.getByLabelText("The edited file");
  await expect.element(input).toHaveAttribute("accept", ".docx");
  await expect
    .element(input)
    .toHaveAccessibleDescription("The file you saved, up to 25 MB. Or drop it here.");
  await input.upload(new File(["x"], "brief.docx"));
  expect(chosen).toEqual(["brief.docx"]);
  expect(await axeViolations(screen.container)).toEqual([]);
});

test("a file dropped on the zone is given too, the first of several, unless it is disabled", async () => {
  const chosen: string[] = [];
  const onFile = (file: File) => chosen.push(file.name);
  const screen = await render(<FileChooser label="The edited file" onFile={onFile} />);
  const zone = screen.container.firstElementChild as Element;
  drop(zone, new File(["a"], "one.docx"), new File(["b"], "two.docx"));
  expect(chosen).toEqual(["one.docx"]);
  drop(zone);
  expect(chosen).toEqual(["one.docx"]);
  await screen.rerender(<FileChooser label="The edited file" onFile={onFile} disabled />);
  drop(zone, new File(["c"], "three.docx"));
  expect(chosen).toEqual(["one.docx"]);
  await expect.element(screen.getByLabelText("The edited file")).toBeDisabled();
});

test("with several allowed, each file chosen or dropped is given in turn", async () => {
  const chosen: string[] = [];
  const screen = await render(
    <FileChooser label="Upload files" multiple onFile={(file) => chosen.push(file.name)} />,
  );
  const input = screen.getByLabelText("Upload files");
  await expect.element(input).toHaveAttribute("multiple");
  await expect.element(input).toHaveAccessibleDescription("Or drop them here.");
  await input.upload([new File(["a"], "one.docx"), new File(["b"], "two.pdf")]);
  drop(screen.container.firstElementChild as Element, new File(["c"], "three.docx"));
  expect(chosen).toEqual(["one.docx", "two.pdf", "three.docx"]);
});

test("a file dragged over the zone marks it, over its children too, and leaving unmarks it", async () => {
  const screen = await render(<FileChooser label="The edited file" onFile={() => undefined} />);
  const zone = screen.container.firstElementChild as HTMLElement;
  const label = zone.querySelector("label") as HTMLElement;
  const drag = (on: HTMLElement, type: string) =>
    on.dispatchEvent(new DragEvent(type, { bubbles: true, cancelable: true }));
  drag(zone, "dragenter");
  await expect.poll(() => zone.dataset.over).toBe("true");
  drag(label, "dragenter");
  drag(zone, "dragleave");
  await expect.poll(() => zone.dataset.over).toBe("true");
  drag(label, "dragleave");
  await expect.poll(() => zone.dataset.over).toBeUndefined();
});

test("progress names what it measures, and says its share", async () => {
  const screen = await render(
    <div>
      <Progress label="Checking in brief.docx" value={3} max={8} valueText="3 bytes of 8 bytes" />
      <Progress label="Nothing yet" value={0} max={0} />
    </div>,
  );
  const bar = screen.getByRole("progressbar", { name: "Checking in brief.docx" });
  await expect.element(bar).toHaveAttribute("aria-valuenow", "38");
  await expect.element(bar).toHaveAttribute("aria-valuetext", "3 bytes of 8 bytes");
  await expect.element(screen.getByText("38%")).toBeVisible();
  await expect
    .element(screen.getByRole("progressbar", { name: "Nothing yet" }))
    .toHaveAttribute("aria-valuenow", "0");
  expect(await axeViolations(screen.container)).toEqual([]);
});

test("the browser's own control isn't drawn: a kit button stands for it, shows its focus, and opens it", async () => {
  const screen = await render(
    <FileChooser label="Upload files" multiple onFile={() => undefined} />,
  );
  const input = screen.getByLabelText("Upload files");
  // Named by its label, and by the button's words, which are its second label.
  await expect.element(input).toHaveAccessibleName("Upload files Choose files");
  expect(input.element().getBoundingClientRect().width).toBeLessThanOrEqual(1);
  const button = screen.getByText("Choose files");
  await expect.element(button).toBeVisible();
  expect(button.element().getAttribute("for")).toBe(input.element().id);
  await userEvent.tab();
  expect(input.element()).toBe(document.activeElement);
  expect(getComputedStyle(button.element()).outlineColor).toBe(token("focus"));
  expect(screen.getByText("No file chosen").elements()).toHaveLength(0);
});

test("the kit button opens the input, and says a file where one is chosen", async () => {
  const screen = await render(<FileChooser label="The edited file" onFile={() => undefined} />);
  const input = screen.getByLabelText("The edited file").element();
  let opened = 0;
  // A click on the button is a click on the input it labels, which opens the picker.
  input.addEventListener("click", (event) => {
    opened += 1;
    event.preventDefault();
  });
  await screen.getByText("Choose a file").click();
  expect(opened).toBe(1);
});

test("a disabled chooser's button keeps its disabled look under the pointer", async () => {
  const screen = await render(
    <FileChooser label="The edited file" disabled onFile={() => undefined} />,
  );
  const button = screen.getByText("Choose a file");
  await button.hover();
  expect(getComputedStyle(button.element()).backgroundColor).toBe(token("line"));
});

test("under forced colours the button still shows the input's focus", async () => {
  onTestFinished(() => commands.forcedColors(false));
  await commands.forcedColors(true);
  const screen = await render(
    <FileChooser label="Upload files" multiple onFile={() => undefined} />,
  );
  await userEvent.tab();
  expect(getComputedStyle(screen.getByText("Choose files").element()).outlineStyle).not.toBe(
    "none",
  );
});
