/**
 * Session replay in the app (lattice RFC-0008, portalr ADR-0077), loaded where the deployment
 * records replays: the person's answer, in the account menu beside analytics', and the recorder
 * that starts once they have said yes to both. Its words and its answer are kept out of the first
 * page's bytes; the recorder, and rrweb with it, is fetched only after the yes.
 */

import { type Api, answerReplayConsent, type Consent, readReplayConsent } from "@portalr/client";
import type { ReplayAnswer } from "@portalr/ui";
import { useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { useAnswering, useRead } from "../answers";

const replayKey = (user: string) => ["portalr", "analytics", "replay", user] as const;

/**
 * The person's answer to replay, read from the relay and believed no longer than the window is
 * unfocused: it is the relay's own, never the switch's guess. The relay withdraws it with
 * analytics', so what was read is set to no when analytics' answer is no, and a later yes to
 * analytics finds none to start from.
 */
function useReplayRead(api: Api, user: string, analytics: boolean, poll: boolean) {
  const client = useQueryClient();
  const before = useRef(analytics);
  useEffect(() => {
    // A no that was a yes: the relay has withdrawn replay, so what was read is no longer its answer
    // and a read still in flight may be the old one. Replay is off until the relay says otherwise,
    // even if it can't be asked.
    if (before.current && !analytics) {
      const key = replayKey(user);
      void client
        .cancelQueries({ queryKey: key })
        .then(() => client.setQueryData<Consent>(key, { given: false, deleting: false }));
    }
    before.current = analytics;
  }, [client, user, analytics]);
  return useRead(api, replayKey(user), readReplayConsent, true, poll, true);
}

/** The privacy guide's account of session replay: what is recorded, and how it is kept. */
const GUIDE = "https://lattice.alexnodeland.com/portalr/guides/privacy/#session-replay";

/** What the menu says while a deletion of recordings isn't done yet, as the switch's own note. */
const STILL_DELETING =
  "Deleting your recordings hasn't finished yet. It will be retried until it is done.";

/** The switch's words, as the owner approved them. */
const WORDS = {
  label: "Record my sessions to improve the app",
  about:
    "Records the layout of the pages you visit and where you click. All text and anything you type is hidden, and chats, files, mini apps and Access are never recorded. Turning it off deletes your recordings.",
  link: "What is recorded, and how it is kept (opens in a new tab)",
  pending: STILL_DELETING,
};

/**
 * Replay's switch beside analytics' in the account menu `children` draws, and its status, said
 * apart from analytics': both are there before an answer changes, so a screen reader hears it.
 */
export function ReplayAccount({
  api,
  user,
  analytics,
  notSaved,
  children,
}: {
  api: Api;
  user: string;
  /** Whether the person has said yes to analytics, which replay rests on. */
  analytics: boolean;
  /** What a screen reader hears when an answer wasn't recorded. */
  notSaved: string;
  /** The account menu, given the answer to put in its Privacy group. */
  children: (replay: ReplayAnswer) => ReactNode;
}) {
  const consent = useReplayRead(api, user, analytics, true);
  const { answer, failed } = useAnswering(api, replayKey(user), answerReplayConsent, false);
  const said = consent.given
    ? "Recording your sessions is on."
    : consent.deleting
      ? `Recording your sessions is off. ${STILL_DELETING}`
      : "Recording your sessions is off.";
  return (
    <>
      {children({
        given: consent.given,
        onAnswer: answer,
        deleting: consent.deleting,
        guide: GUIDE,
        words: WORDS,
      })}
      <span role="status" className="sr-only">
        {failed ? `${notSaved} ${said}` : said}
      </span>
    </>
  );
}

const loadRecorder = () => import("./replay");

/** How long after the relay stops a recording it is tried again, in milliseconds. */
const AGAIN = 60_000;

/**
 * The layout of the pages the person opens in the tenant, and where they click, recorded with
 * their yes to replay as well as to analytics: rrweb is fetched then, and not before. A no, or
 * leaving the tenant, closes it: what waits is dropped.
 */
export function Recording({
  api,
  user,
  tenant,
  analytics,
}: {
  api: Api;
  user: string;
  tenant: string;
  /** Whether the person has said yes to analytics, which replay rests on. */
  analytics: boolean;
}) {
  const given = useReplayRead(api, user, analytics, false).given;
  const client = useQueryClient();
  const recording = analytics && given;
  // A recording the relay stopped is tried again in a minute, if the person's yes is still read.
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!recording) {
      return;
    }
    let live = true;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let opened: InstanceType<Awaited<ReturnType<typeof loadRecorder>>["Recorder"]> | null = null;
    loadRecorder()
      .then(({ Recorder }) => {
        if (live) {
          opened = new Recorder(api, tenant, undefined, () => {
            void client.invalidateQueries({ queryKey: replayKey(user) });
            retry = setTimeout(() => setAttempt((now) => now + 1), AGAIN);
          });
          opened.start();
        }
      })
      .catch(() => {
        // The chunk didn't load: nothing is recorded, and the screen is as it was.
      });
    return () => {
      live = false;
      clearTimeout(retry);
      opened?.close();
    };
  }, [api, client, tenant, user, recording, attempt]);
  return null;
}
