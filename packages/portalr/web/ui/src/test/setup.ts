import "../rail.css";
import { beforeEach } from "vitest";
import { commands } from "vitest/browser";

// No test starts with the pointer resting on what it renders.
beforeEach(() => commands.pointerAway());
