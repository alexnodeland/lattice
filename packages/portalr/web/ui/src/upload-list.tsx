/**
 * Files being uploaded, one after another (native files ADR-0017): each by its name and size,
 * waiting, going with how far it has gone, or what came of it, in words. The one going can be
 * stopped, one waiting or done with taken off the list, and one whose answer never came, or that
 * the app couldn't finish, sent again. Each control names its file, so a screen reader that lists
 * the buttons tells them apart.
 */

import type { ReactNode } from "react";
import { Alert, type AlertTone } from "./alert";
import { Button } from "./button";
import { fileSize } from "./native-file";
import { Progress } from "./progress";
import { Row, Rows } from "./rows";

/** The bidirectional controls a name could reorder the words around it with. */
const BIDI = /[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]/g;

/** A file's name as shown: without the controls that would reorder what is said around it. */
export const plainName = (name: string) => name.replace(BIDI, "");

/** One file on the list, as the list shows it. */
export interface UploadItem {
  readonly id: string;
  readonly name: string;
  readonly size: number;
  readonly state: "waiting" | "sending" | "done" | "failed";
  /** How many of its bytes have gone, while it is sent. */
  readonly sent?: number;
  /** What came of it, or why it can't go, in words. */
  readonly said?: ReactNode;
  readonly tone?: AlertTone;
  /** Whether sending it again may succeed: its answer never came, or the app couldn't finish. */
  readonly again?: boolean;
}

export function UploadList({
  items,
  onStop,
  onRemove,
  onRetry,
}: {
  items: readonly UploadItem[];
  onStop: (id: string) => void;
  onRemove: (id: string) => void;
  onRetry: (id: string) => void;
}) {
  if (items.length === 0) {
    return null;
  }
  return (
    <Rows label="Uploads">
      {items.map((item) => {
        const name = <bdi>{plainName(item.name)}</bdi>;
        return (
          <Row
            key={item.id}
            name={<span className="break-all font-mono">{name}</span>}
            meta={
              <div className="flex flex-col gap-2">
                {item.state === "sending" ? (
                  <Progress
                    label={`Uploading ${plainName(item.name)}`}
                    shown="Uploading"
                    value={item.sent ?? 0}
                    max={item.size}
                    valueText={`${fileSize(item.sent ?? 0)} of ${fileSize(item.size)}`}
                  />
                ) : (
                  <span>
                    {fileSize(item.size)}
                    {item.state === "waiting" && ", waiting"}
                  </span>
                )}
                {item.said !== undefined && (
                  <Alert tone={item.tone ?? "info"} live={false}>
                    {item.said}
                  </Alert>
                )}
                <div className="flex flex-wrap gap-2">
                  {item.state === "sending" && (
                    <Button variant="secondary" size="sm" onClick={() => onStop(item.id)}>
                      Stop
                      <span className="sr-only"> uploading {name}</span>
                    </Button>
                  )}
                  {item.state === "failed" && item.again && (
                    <Button size="sm" onClick={() => onRetry(item.id)}>
                      Try again
                      <span className="sr-only"> to upload {name}</span>
                    </Button>
                  )}
                  {item.state !== "sending" && (
                    <Button variant="secondary" size="sm" onClick={() => onRemove(item.id)}>
                      {item.state === "waiting" ? "Don't upload" : "Dismiss"}
                      <span className="sr-only"> {name}</span>
                    </Button>
                  )}
                </div>
              </div>
            }
          />
        );
      })}
    </Rows>
  );
}
