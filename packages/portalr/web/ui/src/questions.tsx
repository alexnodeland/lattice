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
import {
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { Alert } from "./alert";
import { Badge } from "./badge";
import { Button } from "./button";
import { cn } from "./cn";
import { FieldGroup } from "./field-group";
import { Icon } from "./icon";
import { glyphs } from "./icons";
import { isObject, isString, own } from "./json";
import { type Sent, Unsent, useSending } from "./sending";
import { ASKING, FEEDBACK, RING } from "./states";
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
        "flex flex-col gap-4 rounded-(--question-radius) border border-line bg-surface p-(--question-pad) text-sm",
        given === null && ASKING,
      )}
    >
      <p className={cn(TYPE.meta, "inline-flex items-center gap-2")}>
        <Icon icon={glyphs.bot} className={cn("size-4", given === null && "text-accent")} />
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

/** A step of a stepped ask: one of the questions, or, past them, the review. */
function unansweredAt(questions: readonly Question[], choosing: readonly Choosing[]) {
  return questions.map((question, at) => unanswered(question, choosing[at] as Choosing));
}

/**
 * The questions as a form, sent once every one is answered. More than one is stepped (portalr
 * ADR-0080): one question a view, Back and Next between them, "2 of 3" said as it moves and a
 * dot per question that fills as it is answered, then a review of every answer with a way back
 * to change each, and one Answer that sends them all as one reply, as a single question is sent.
 * Each step lands the focus on the question's words; Enter goes on to the next step, and the
 * arrow keys do where the focus isn't in an option or a field. Nothing slides: a step is a cut.
 */
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
  const stepped = questions.length > 1;
  // The step: a question's index, or, past the last, the review.
  const [step, setStep] = useState(0);
  const review = stepped && step === questions.length;
  // Whether the step was moved to by the reader, whose focus then lands on its words.
  const moved = useRef(false);
  const progress = useId();
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
  useEffect(() => {
    if (moved.current) {
      moved.current = false;
      form.current?.querySelector<HTMLElement>("[data-step-heading]")?.focus();
    }
  }, [step]);
  function choose(at: number, change: Choosing) {
    setChoosing((all) => all.map((each, index) => (index === at ? change : each)));
    setErrors((all) => all.map((each, index) => (index === at ? null : each)));
  }
  /** To the words, if they are what's missing, or else to the question's first option. */
  function attend() {
    const asked = form.current?.querySelector<HTMLElement>("[data-question]");
    (
      asked?.querySelector<HTMLElement>("[data-words]") ??
      asked?.querySelector<HTMLElement>("[role=radio], [role=checkbox]")
    )?.focus();
  }
  function go(to: number) {
    moved.current = true;
    setStep(to);
  }
  /** On to the next step, once this question is answered. */
  function next() {
    const found = unanswered(questions[step] as Question, choosing[step] as Choosing);
    if (found !== null) {
      setErrors((all) => all.map((each, at) => (at === step ? found : each)));
      attend();
      return;
    }
    go(step + 1);
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (stepped && !review) {
      next();
      return;
    }
    const found = unansweredAt(questions, choosing);
    setErrors(found);
    const first = found.findIndex((error) => error !== null);
    if (first !== -1) {
      if (stepped) {
        go(first);
      }
      requestAnimationFrame(attend);
      return;
    }
    const answers = choosing.map(({ selected, other }) => ({
      selected: [...selected],
      ...(other !== null && { other: other.trim() }),
    }));
    setSent(await send(() => onAnswer({ answers })));
  }
  function keys(event: KeyboardEvent<HTMLFormElement>) {
    if (!stepped || closed) {
      return;
    }
    const at = event.target as HTMLElement;
    if (at.closest("[role=radio], [role=checkbox], input, textarea, button")) {
      return;
    }
    // On, and back, in the writing's direction: in a right-to-left page the arrows swap.
    const rtl = getComputedStyle(event.currentTarget).direction === "rtl";
    const [on, back] = rtl ? ["ArrowLeft", "ArrowRight"] : ["ArrowRight", "ArrowLeft"];
    if (event.key === on && !review) {
      event.preventDefault();
      next();
    } else if (event.key === back && step > 0) {
      event.preventDefault();
      go(step - 1);
    }
  }
  const closed = sent || pending;
  const answered = unansweredAt(questions, choosing).map((error) => error === null);
  return (
    <form
      ref={form}
      aria-label="The agent asks"
      aria-describedby={stepped ? progress : undefined}
      className="flex flex-col gap-5"
      onSubmit={submit}
      onKeyDown={keys}
    >
      {stepped && (
        <div className="flex items-center justify-end gap-3">
          <p id={progress} aria-live="polite" className={cn(TYPE.note, "tabular-nums")}>
            {review ? "Review your answers" : `Step ${step + 1} of ${questions.length}`}
          </p>
          {/* Three bars: what is done, where we are, and what is next (portalr ADR-0081). */}
          <span aria-hidden="true" className="flex items-center gap-1">
            {questions.map((question, at) => (
              <span
                key={question.question}
                className={cn(
                  "h-1 w-3 rounded-full",
                  at === step && !review
                    ? "bg-accent"
                    : answered[at] || review
                      ? "bg-accent opacity-45"
                      : "bg-edge",
                )}
              />
            ))}
          </span>
        </div>
      )}
      {review ? (
        <Review questions={questions} choosing={choosing} onChange={go} />
      ) : (
        questions.map(
          (question, at) =>
            (!stepped || at === step) && (
              <Asked
                key={question.question}
                question={question}
                choosing={choosing[at] as Choosing}
                error={errors[at] ?? null}
                disabled={closed}
                stepped={stepped}
                onChange={(change) => choose(at, change)}
              />
            ),
        )
      )}
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap gap-2">
          {stepped && step > 0 && (
            <Button
              type="button"
              variant="secondary"
              disabled={closed}
              onClick={() => go(step - 1)}
            >
              Back
            </Button>
          )}
          {/* Keyed apart: React reusing one button for both would make the click that reached
              the review submit it, as the node turned into the submit button under the pointer. */}
          {/* The step's own next move, which a phone's thumb bar mirrors (portalr ADR-0082). */}
          {stepped && !review ? (
            <Button key="next" type="button" onClick={next} disabled={closed} data-thumb-action="">
              Next
            </Button>
          ) : (
            <Button
              key="answer"
              type="submit"
              disabled={sent}
              pending={pending}
              data-thumb-action=""
            >
              Answer
            </Button>
          )}
        </div>
        <p className={TYPE.note}>Or reply in a message, in your own words.</p>
      </div>
      <Unsent reason={unsent} />
    </form>
  );
}

/** The review before the answers go: each question's answer, and a way back to change it. */
function Review({
  questions,
  choosing,
  onChange,
}: {
  questions: readonly Question[];
  choosing: readonly Choosing[];
  onChange: (at: number) => void;
}) {
  return (
    <dl className="flex flex-col gap-2">
      <dt className="sr-only">Your answers</dt>
      {questions.map((question, at) => {
        const chosen = choosing[at] as Choosing;
        const said = [...chosen.selected, ...(chosen.other ? [chosen.other.trim()] : [])];
        return (
          <div
            key={question.question}
            className="flex items-center justify-between gap-3 rounded-(--button-radius) bg-subtle px-3 py-2"
          >
            <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
              <span aria-hidden="true" className="font-mono text-muted text-xs tabular-nums">
                {at + 1}
              </span>
              <dt className="flex min-w-0 flex-wrap items-baseline gap-x-2">
                <Header>{question.header}</Header>
                <span
                  data-step-heading={at === 0 ? "" : undefined}
                  tabIndex={at === 0 ? -1 : undefined}
                  className="text-muted outline-none"
                >
                  {question.question}
                </span>
              </dt>
              <dd className="font-medium text-fg">{said.join(", ") || "Not answered"}</dd>
            </div>
            <Button type="button" variant="ghost" size="sm" onClick={() => onChange(at)}>
              Change<span className="sr-only"> {question.header}</span>
            </Button>
          </div>
        );
      })}
    </dl>
  );
}

/** A question's header, as a chip. */
function Header({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex max-w-full shrink-0 items-center truncate rounded-(--question-chip-radius) bg-subtle px-2 py-0.5 font-medium text-muted text-xs">
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
  stepped = false,
  onChange,
}: {
  question: Question;
  choosing: Choosing;
  error: string | null;
  disabled: boolean;
  /** Whether it is one step of several, whose words take the focus as the step is shown. */
  stepped?: boolean;
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
      <span
        data-step-heading={stepped ? "" : undefined}
        tabIndex={stepped ? -1 : undefined}
        className={cn(TYPE.subsection, "outline-none")}
      >
        {question.question}
      </span>
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
export const ROW = cn(
  "group flex w-full cursor-pointer items-start gap-3 rounded-(--question-option-radius) border border-line bg-surface px-(--question-option-pad-x) py-(--question-option-pad-y) text-start hover:border-edge data-checked:border-accent data-checked:bg-wash data-disabled:cursor-not-allowed data-disabled:hover:border-line",
  RING,
  FEEDBACK,
);

/** The mark in an option's row: a ring, or a box, filled in the working colour once checked. */
export const MARK = cn(
  "mt-0.5 grid size-4 shrink-0 place-items-center border border-edge bg-surface group-data-checked:border-accent",
  FEEDBACK,
);

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
          <Badge tone="accent" id={`${id}-recommended`}>
            Recommended
          </Badge>
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
          <Icon icon={glyphs.check} className="size-3" />
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
              <div key={question.question} className="flex flex-col items-start gap-1">
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
