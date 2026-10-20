/**
 * What the agent asks through `ask_user` (artifactr ADR-0083): one to four questions, each a
 * group of options to choose one or several of, the agent's recommendation first, and, where it
 * offers it, an answer in the reader's own words. Answered, it stays in the thread and says what
 * was chosen, and by whom.
 */

import { Checkbox } from "@base-ui/react/checkbox";
import { CheckboxGroup } from "@base-ui/react/checkbox-group";
import { Radio } from "@base-ui/react/radio";
import { RadioGroup } from "@base-ui/react/radio-group";
import type { ArtifactrV1 } from "@portalr/client";
import { Bot, Check } from "lucide-react";
import { type FormEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";
import { Alert } from "./alert";
import { Button } from "./button";
import { cn } from "./cn";
import { FieldGroup } from "./field-group";
import { Icon } from "./icon";
import { isObject, isString, own } from "./json";
import { type Sent, Unsent, useSending } from "./sending";
import { TextField } from "./text-field";
import { TYPE } from "./type";

type Option = ArtifactrV1.Option;
/** A question as it is read: its options in the order they are shown. */
type Question = Omit<ArtifactrV1.Question, "options"> & { readonly options: readonly Option[] };
type Chosen = ArtifactrV1.Chosen;
export type QuestionsAnswer = ArtifactrV1.AskUserAnswer;

/** The value of the choice to answer in one's own words: no option's, since a label isn't empty. */
const OTHER = "";

/** The questions a request asks, recommended options first, or null if its arguments aren't. */
export function readQuestions(args: unknown): readonly Question[] | null {
  const questions = isObject(args) ? own(args, "questions") : undefined;
  if (!(Array.isArray(questions) && questions.length > 0 && questions.every(isQuestion))) {
    return null;
  }
  return questions.map((question) => ({
    ...question,
    options: [...question.options].sort(
      (a, b) => Number(b.recommended ?? false) - Number(a.recommended ?? false),
    ),
  }));
}

function isQuestion(value: unknown): value is Question {
  if (!(isObject(value) && isString(value.question) && isString(value.header))) {
    return false;
  }
  const { options } = value;
  return Array.isArray(options) && options.every((o) => isObject(o) && isString(o.label));
}

/** An answer as the log holds it: answers per question, or a reply; null if it is neither. */
export function readAnswer(value: unknown): QuestionsAnswer | null {
  if (isObject(value) && isString(value.reply)) {
    return { reply: value.reply };
  }
  const answers = isObject(value) ? own(value, "answers") : undefined;
  return Array.isArray(answers) && answers.every(isObject)
    ? { answers: answers as Chosen[] }
    : null;
}

/** What one question has chosen so far: labels, and the reader's own words, or null for none. */
interface Choosing {
  readonly selected: readonly string[];
  readonly other: string | null;
}

/** Why a question can't be sent as it is, or null when it can. */
function unanswered(question: Question, choosing: Choosing): string | null {
  if (choosing.other !== null && choosing.other.trim() === "") {
    return "Write your answer, or choose an option.";
  }
  if (choosing.selected.length === 0 && choosing.other === null) {
    return question.multiple ? "Choose at least one." : "Choose one.";
  }
  return null;
}

/**
 * The agent's questions, asked through `ask_user`: a form until it is answered, then what was
 * chosen. It takes the focus as it appears, unless `focus` says another should, and answers once,
 * with every question's answer. `answer` is the answer the log holds, and `answeredBy` who gave
 * it, as the thread names them.
 */
export function Questions({
  request,
  answer = null,
  answeredBy = null,
  focus = true,
  onAnswer,
}: {
  request: ArtifactrV1.DeferredRequest;
  answer?: unknown;
  answeredBy?: string | null;
  focus?: boolean;
  onAnswer: (answer: QuestionsAnswer) => Sent;
}) {
  const questions = readQuestions(request.args);
  const given = answer === null ? null : readAnswer(answer);
  return (
    <section
      aria-label={given === null ? "The agent asks" : "The agent asked"}
      className={cn(
        "flex flex-col gap-4 rounded-lg border bg-surface p-4 text-sm",
        given === null ? "border-accent" : "border-line",
      )}
    >
      <p className={cn(TYPE.note, "inline-flex items-center gap-1.5")}>
        <Icon icon={Bot} className="size-3.5" />
        {given === null ? "The agent asks" : "The agent asked"}
      </p>
      {questions === null ? (
        <Alert tone="warn" live={false}>
          These questions can't be shown here. Reply in a message to answer them.
        </Alert>
      ) : given === null ? (
        <Asking questions={questions} focus={focus} onAnswer={onAnswer} />
      ) : (
        <Answered questions={questions} answer={given} by={answeredBy} />
      )}
    </section>
  );
}

/** The questions as a form, sent once every one is answered. */
function Asking({
  questions,
  focus,
  onAnswer,
}: {
  questions: readonly Question[];
  focus: boolean;
  onAnswer: (answer: QuestionsAnswer) => Sent;
}) {
  const [choosing, setChoosing] = useState<readonly Choosing[]>(() =>
    questions.map(() => ({ selected: [], other: null })),
  );
  const [errors, setErrors] = useState<readonly (string | null)[]>(() => questions.map(() => null));
  const [sent, setSent] = useState(false);
  const { pending, unsent, send } = useSending();
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (!focus) {
      return;
    }
    // A frame later, once Base UI's groups have their options: focused before, a radio group's
    // arrow keys wouldn't move from it.
    const first = requestAnimationFrame(() =>
      form.current?.querySelector<HTMLElement>("[role=radio], [role=checkbox]")?.focus(),
    );
    return () => cancelAnimationFrame(first);
  }, [focus]);
  function choose(at: number, change: Choosing) {
    setChoosing((all) => all.map((each, index) => (index === at ? change : each)));
    setErrors((all) => all.map((each, index) => (index === at ? null : each)));
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = questions.map((question, at) => unanswered(question, choosing[at] as Choosing));
    setErrors(found);
    const first = found.findIndex((error) => error !== null);
    if (first !== -1) {
      // To the words, if they are what's missing, or else to the question's first option.
      const asked = form.current?.querySelectorAll<HTMLElement>("[data-question]")[first];
      (
        asked?.querySelector<HTMLElement>("[data-words]") ??
        asked?.querySelector<HTMLElement>("[role=radio], [role=checkbox]")
      )?.focus();
      return;
    }
    const answers = choosing.map(({ selected, other }) => ({
      selected: [...selected],
      ...(other !== null && { other: other.trim() }),
    }));
    setSent(await send(() => onAnswer({ answers })));
  }
  const closed = sent || pending;
  return (
    <form ref={form} aria-label="The agent asks" className="flex flex-col gap-5" onSubmit={submit}>
      {questions.map((question, at) => (
        <Asked
          // biome-ignore lint/suspicious/noArrayIndexKey: the questions never change order
          key={at}
          question={question}
          choosing={choosing[at] as Choosing}
          error={errors[at] ?? null}
          disabled={closed}
          onChange={(change) => choose(at, change)}
        />
      ))}
      <div className="flex flex-col gap-1">
        <Button type="submit" className="self-start" disabled={closed}>
          Answer
        </Button>
        <p className={TYPE.note}>Or reply in a message, in your own words.</p>
      </div>
      <Unsent reason={unsent} />
    </form>
  );
}

/** A question's header, as a chip. */
function Header({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex max-w-full shrink-0 items-center truncate rounded-full border border-line bg-wash px-2 py-0.5 font-semibold text-fg text-xs">
      {children}
    </span>
  );
}

/** One question: its header and words, and its options, as a radio or a checkbox group. */
function Asked({
  question,
  choosing,
  error,
  disabled,
  onChange,
}: {
  question: Question;
  choosing: Choosing;
  error: string | null;
  disabled: boolean;
  onChange: (change: Choosing) => void;
}) {
  const words = useRef<HTMLInputElement>(null);
  const writing = choosing.other !== null;
  const wasWriting = useRef(writing);
  useEffect(() => {
    if (writing && !wasWriting.current) {
      words.current?.focus();
    }
    wasWriting.current = writing;
  }, [writing]);
  const options = [
    ...question.options.map((option) => ({ ...option, value: option.label })),
    ...(question.other
      ? [{ label: "Other", description: "Answer in your own words", value: OTHER }]
      : []),
  ];
  // The labels chosen, and the choice to answer in one's own words while it is.
  const chosen = [...choosing.selected, ...(writing ? [OTHER] : [])];
  const choose = (values: readonly string[]) =>
    onChange({
      selected: values.filter((value) => value !== OTHER),
      other: values.includes(OTHER) ? (choosing.other ?? "") : null,
    });
  const rows = options.map((option) => (
    <OptionRow key={option.value} option={option} multiple={question.multiple ?? false} />
  ));
  const label = (
    <span className="flex flex-col items-start gap-1.5">
      <Header>{question.header}</Header>
      <span className="font-semibold text-base text-fg">{question.question}</span>
    </span>
  );
  return (
    <div data-question className="flex flex-col gap-2">
      <FieldGroup
        label={label}
        hint={question.multiple ? "Choose any that apply." : undefined}
        error={error}
      >
        {(grouped) =>
          question.multiple ? (
            <CheckboxGroup
              {...grouped}
              value={chosen}
              disabled={disabled}
              onValueChange={choose}
              className="flex flex-col gap-1.5 pt-1"
            >
              {rows}
            </CheckboxGroup>
          ) : (
            <RadioGroup
              {...grouped}
              value={chosen[0] ?? null}
              disabled={disabled}
              onValueChange={(value: string | null) => choose(value === null ? [] : [value])}
              className="flex flex-col gap-1.5 pt-1"
            >
              {rows}
            </RadioGroup>
          )
        }
      </FieldGroup>
      {writing && (
        <TextField
          ref={words}
          data-words
          label="Your answer"
          value={choosing.other ?? ""}
          disabled={disabled}
          onValueChange={(value) => onChange({ ...choosing, other: String(value) })}
        />
      )}
    </div>
  );
}

/** An option's row, which is its control: checked, it is edged and washed in the working colour. */
const ROW =
  "group flex w-full cursor-pointer items-start gap-3 rounded-md border border-line bg-surface px-3 py-2.5 text-start outline-offset-2 hover:border-edge focus-visible:outline-2 focus-visible:outline-focus data-checked:border-accent data-checked:bg-wash data-disabled:cursor-not-allowed data-disabled:hover:border-line";

/** The mark in an option's row: a ring, or a box, filled in the working colour once checked. */
const MARK =
  "mt-0.5 grid size-4 shrink-0 place-items-center border border-edge bg-surface group-data-checked:border-accent";

/**
 * One option, as a row that is its radio or its checkbox, so the whole of it chooses it: named by
 * its label, and its badge where the agent recommends it, and described by what it means.
 */
function OptionRow({
  option,
  multiple,
}: {
  option: Option & { value: string };
  multiple: boolean;
}) {
  const id = useId();
  const named = {
    "aria-labelledby": `${id}-label${option.recommended ? ` ${id}-recommended` : ""}`,
    ...(option.description && { "aria-describedby": `${id}-description` }),
  };
  const words = (
    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
      <span className="flex flex-wrap items-center gap-2">
        <span id={`${id}-label`} className="font-semibold text-fg">
          {option.label}
        </span>
        {option.recommended && (
          <span
            id={`${id}-recommended`}
            className="rounded-full bg-accent px-1.5 py-px font-semibold text-on-accent text-xs"
          >
            Recommended
          </span>
        )}
      </span>
      {option.description && (
        <span id={`${id}-description`} className="text-muted">
          {option.description}
        </span>
      )}
    </span>
  );
  return multiple ? (
    <Checkbox.Root {...named} value={option.value} className={ROW}>
      <span className={cn(MARK, "rounded group-data-checked:bg-accent")}>
        <Checkbox.Indicator className="text-on-accent">
          <Icon icon={Check} className="size-3" />
        </Checkbox.Indicator>
      </span>
      {words}
    </Checkbox.Root>
  ) : (
    <Radio.Root {...named} value={option.value} className={ROW}>
      <span className={cn(MARK, "rounded-full")}>
        <Radio.Indicator className="size-2 rounded-full bg-accent" />
      </span>
      {words}
    </Radio.Root>
  );
}

/** What was chosen for each question, or the reply that answered them, and by whom. */
function Answered({
  questions,
  answer,
  by,
}: {
  questions: readonly Question[];
  answer: QuestionsAnswer;
  by: string | null;
}) {
  return (
    <>
      {"reply" in answer ? (
        <p className="flex flex-col gap-0.5">
          <span className="text-muted">Answered in a message:</span>
          <span className="text-fg">{answer.reply}</span>
        </p>
      ) : (
        <dl className="flex flex-col gap-3">
          {questions.map((question, at) => {
            const chosen = answer.answers[at];
            const said = [...(chosen?.selected ?? []), ...(chosen?.other ? [chosen.other] : [])];
            return (
              // biome-ignore lint/suspicious/noArrayIndexKey: the questions never change order
              <div key={at} className="flex flex-col items-start gap-1">
                <dt className="flex flex-col items-start gap-1.5">
                  <Header>{question.header}</Header>
                  <span className="text-muted">{question.question}</span>
                </dt>
                <dd className="font-semibold text-fg">{said.join(", ")}</dd>
              </div>
            );
          })}
        </dl>
      )}
      {by !== null && <p className={TYPE.note}>Answered by {by}</p>}
    </>
  );
}
