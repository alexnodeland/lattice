import { expect, onTestFinished, test } from "vitest";
import { commands } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Switch } from "./switch";
import { token } from "./test/colours";

test("a switch turns on, and its track takes the working colour", async () => {
  const screen = await render(<Switch aria-label="Notices" />);
  const control = screen.getByRole("switch", { name: "Notices" });
  await expect.element(control).not.toBeChecked();
  await control.click();
  await expect.element(control).toBeChecked();
  expect(getComputedStyle(control.element()).backgroundColor).toBe(token("accent"));
});

test("a disabled switch doesn't turn", async () => {
  const screen = await render(<Switch aria-label="Digest" disabled />);
  const control = screen.getByRole("switch", { name: "Digest" });
  await control.click({ force: true });
  await expect.element(control).not.toBeChecked();
});

test("a caller's classes merge with the switch's", async () => {
  const screen = await render(<Switch aria-label="Alerts" className="bg-surface" />);
  const track = screen.getByRole("switch", { name: "Alerts" }).element();
  expect(track.classList).toContain("bg-surface");
  expect(track.classList).not.toContain("bg-paper");
  expect(track.classList).toContain("rounded-full");
});

test("under forced colours a switch keeps the system's colours, on and off apart", async () => {
  onTestFinished(() => commands.forcedColors(false));
  const screen = await render(
    <div>
      <Switch aria-label="On" defaultChecked />
      <Switch aria-label="Off" />
    </div>,
  );
  await commands.forcedColors(true);
  const fills = (name: string) => {
    const track = screen.getByRole("switch", { name }).element();
    const thumb = track.firstElementChild as Element;
    expect(getComputedStyle(track).forcedColorAdjust, name).toBe("none");
    return [getComputedStyle(track).backgroundColor, getComputedStyle(thumb).backgroundColor];
  };
  const [onTrack, onThumb] = fills("On");
  const [offTrack, offThumb] = fills("Off");
  expect(onThumb).not.toBe(onTrack);
  expect(offThumb).not.toBe(offTrack);
  expect(onTrack).not.toBe(offTrack);
});
