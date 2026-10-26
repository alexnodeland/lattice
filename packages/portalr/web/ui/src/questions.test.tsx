import type { ArtifactrV1 } from "@portalr/client";
import { describe, expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Request } from "./chat";
import { Questions, readAnswer, readQuestions } from "./questions";
import { token } from "./test/colours";

const sent = (outcome: "done" | "refused" | "closed" = "done") => vi.fn(async () => ({ outcome }));

const WEEK = {
  question: "Which week?",
  header: "Week",
  options: [
    { label: "This week", description: "Starting Monday" },
    { label: "The next", description: "A week to prepare", recommended: true },
  ],
  other: true,
};
const TOPICS = {
  question: "What should the notes cover?",
  header: "Topics",
  options: [{ label: "Agenda" }, { label: "Decisions" }, { label: "Actions" }],
  multiple: true,
};

const asking = (...questions: object[]): ArtifactrV1.DeferredRequest => ({
  kind: "question",
  tool_call_id: "q1",
  tool_name: "ask_user",
  args: { questions } as ArtifactrV1.Args,
});

describe("what ask_user asks", () => {
  test("is read with its recommended options first, or not at all", () => {
    expect(readQuestions(asking(WEEK).args)?.[0]?.options.map(({ label }) => label)).toEqual([
      "The next",
      "This week",
    ]);
    expect(readQuestions({ question: "Which week?" })).toBeNull();
    expect(readQuestions({ questions: [] })).toBeNull();
    expect(readQuestions({ questions: [{ ...WEEK, options: [{ value: 1 }] }] })).toBeNull();
    expect(readQuestions({ questions: [{ header: "Week" }] })).toBeNull();
    expect(readQuestions(null)).toBeNull();
  });

  test("is answered per question, or by a reply", () => {
    expect(readAnswer({ answers: [{ selected: ["The next"] }] })).toEqual({
      answers: [{ selected: ["The next"] }],
    });
    expect(readAnswer({ reply: "Whenever" })).toEqual({ reply: "Whenever" });
    expect(readAnswer("The next")).toBeNull();
    expect(readAnswer({ answers: ["The next"] })).toBeNull();
  });
});

test("each question is a group named by its header and words, its options named by their labels", async () => {
  const screen = await render(<Questions request={asking(WEEK, TOPICS)} onAnswer={sent()} />);
  const card = screen.getByRole("region", { name: "The agent asks" });
  const week = card.getByRole("radiogroup", { name: "Week Which week?" });
  await expect.element(week).toBeVisible();
  const radios = week.getByRole("radio").elements();
  expect(radios.map((radio) => radio.getAttribute("aria-labelledby") !== null)).toEqual([
    true,
    true,
    true,
  ]);
  const next = week.getByRole("radio", { name: "The next Recommended" });
  await expect.element(next).toHaveAccessibleDescription("A week to prepare");
  await expect.element(next).toHaveFocus(); // the first, which the agent recommends
  await expect.element(week.getByRole("radio", { name: "Other" })).toBeVisible();
  // Two questions are stepped: the second is a step on, after the first is answered.
  await expect.element(card.getByText("1 of 2")).toBeVisible();
  expect(
    card.getByRole("group", { name: "Topics What should the notes cover?" }).elements(),
  ).toHaveLength(0);
  await next.click();
  await card.getByRole("button", { name: "Next" }).click();
  const topics = card.getByRole("group", { name: "Topics What should the notes cover?" });
  expect(topics.getByRole("checkbox").elements()).toHaveLength(3);
  await expect.element(card.getByText("Choose any that apply.")).toBeVisible();
  await expect.element(card.getByText("2 of 2")).toBeVisible();
});

test("one choice, several, and words of the reader's own are sent as each question's answer", async () => {
  const onAnswer = sent();
  const screen = await render(<Questions request={asking(WEEK, TOPICS)} onAnswer={onAnswer} />);
  await screen.getByRole("radio", { name: "The next Recommended" }).click();
  await userEvent.keyboard("{ArrowDown}"); // to "This week", as a radio group's keys do
  await expect.element(screen.getByRole("radio", { name: "This week" })).toBeChecked();
  await screen.getByRole("radio", { name: "Other" }).click();
  const words = screen.getByRole("textbox", { name: "Your answer" });
  await expect.element(words).toHaveFocus();
  await words.fill("  After the launch ");
  await screen.getByRole("button", { name: "Next" }).click();
  await screen.getByRole("checkbox", { name: "Agenda" }).click();
  await screen.getByRole("checkbox", { name: "Actions" }).click();
  await screen.getByRole("checkbox", { name: "Agenda" }).click();
  await screen.getByRole("checkbox", { name: "Decisions" }).click();
  await screen.getByRole("button", { name: "Next" }).click();
  // The review: each answer, then one Answer sends them all as one reply.
  await expect.element(screen.getByText("Review your answers")).toBeVisible();
  await expect.element(screen.getByText("After the launch")).toBeVisible();
  await expect.element(screen.getByText("Actions, Decisions")).toBeVisible();
  expect(onAnswer).not.toHaveBeenCalled();
  await expect.element(screen.getByRole("button", { name: "Answer" })).toBeEnabled();
  await screen.getByRole("button", { name: "Answer" }).click();
  expect(onAnswer.mock.calls).toEqual([
    [
      {
        answers: [
          { selected: [], other: "After the launch" },
          { selected: ["Actions", "Decisions"] },
        ],
      },
    ],
  ]);
  await expect.element(screen.getByRole("button", { name: "Answer" })).toBeDisabled();
});

test("a question left unanswered says so, and takes the focus, and nothing is sent", async () => {
  const onAnswer = sent();
  const screen = await render(<Questions request={asking(WEEK, TOPICS)} onAnswer={onAnswer} />);
  await screen.getByRole("radio", { name: "Other" }).click();
  await screen.getByRole("button", { name: "Next" }).click();
  await expect.element(screen.getByText("Write your answer, or choose an option.")).toBeVisible();
  await expect.element(screen.getByRole("textbox", { name: "Your answer" })).toHaveFocus();
  await screen.getByRole("radio", { name: "The next Recommended" }).click();
  await expect
    .element(screen.getByRole("textbox", { name: "Your answer" }))
    .not.toBeInTheDocument();
  await screen.getByRole("button", { name: "Next" }).click();
  await screen.getByRole("button", { name: "Next" }).click();
  const topics = screen.getByRole("group", { name: "Topics What should the notes cover?" });
  await expect.element(topics).toHaveAttribute("aria-invalid", "true");
  await expect.element(screen.getByText("Choose at least one.")).toBeVisible();
  await expect.element(topics.getByRole("checkbox", { name: "Agenda" })).toHaveFocus();
  await topics.getByRole("checkbox", { name: "Decisions" }).click();
  await expect.element(screen.getByText("Choose at least one.")).not.toBeInTheDocument();
  expect(onAnswer).not.toHaveBeenCalled();
});

test("a single question unanswered asks for one", async () => {
  const screen = await render(
    <Questions request={asking({ ...WEEK, other: false })} onAnswer={sent()} />,
  );
  await screen.getByRole("button", { name: "Answer" }).click();
  await expect.element(screen.getByText("Choose one.")).toBeVisible();
  expect(screen.getByRole("radio", { name: "Other" }).elements()).toHaveLength(0);
});

test("an answer that wasn't sent can be given again", async () => {
  const screen = await render(
    <Questions request={asking(WEEK)} focus={false} onAnswer={sent("closed")} />,
  );
  await expect
    .element(screen.getByRole("radio", { name: "The next Recommended" }))
    .not.toHaveFocus();
  await screen.getByRole("radio", { name: "The next Recommended" }).click();
  await screen.getByRole("button", { name: "Answer" }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("That wasn't sent: the connection closed.");
  await expect.element(screen.getByRole("button", { name: "Answer" })).toBeEnabled();
});

test("answered, it says what was chosen for each question, and by whom", async () => {
  const answer = {
    answers: [{ selected: [], other: "After the launch" }, { selected: ["Agenda", "Actions"] }],
  };
  const screen = await render(
    <Questions request={asking(WEEK, TOPICS)} answer={answer} answeredBy="You" onAnswer={sent()} />,
  );
  const card = screen.getByRole("region", { name: "The agent asked" });
  await expect.element(card.getByText("After the launch")).toBeVisible();
  await expect.element(card.getByText("Agenda, Actions")).toBeVisible();
  await expect.element(card.getByText("Answered by You")).toBeVisible();
  expect(card.getByRole("radio").elements()).toHaveLength(0);
});

test("answered by a message, it says the reply", async () => {
  const screen = await render(
    <Questions request={asking(WEEK)} answer={{ reply: "Whenever" }} onAnswer={sent()} />,
  );
  await expect.element(screen.getByText("Answered in a message:")).toBeVisible();
  await expect.element(screen.getByText("Whenever")).toBeVisible();
  expect(screen.getByText(/Answered by/).elements()).toHaveLength(0);
});

test("questions it can't read say to reply in a message", async () => {
  const request = { ...asking(), args: { question: "Which week?" } };
  const screen = await render(<Request request={request} onAnswer={sent()} />);
  await expect
    .element(
      screen.getByText("These questions can't be shown here. Reply in a message to answer them."),
    )
    .toBeVisible();
});

test("a request to ask_user is drawn as its questions, and answered with them", async () => {
  const onAnswer = sent();
  const screen = await render(<Request request={asking(WEEK)} onAnswer={onAnswer} />);
  await screen.getByRole("radio", { name: "This week" }).click();
  await screen.getByRole("button", { name: "Answer" }).click();
  expect(onAnswer).toHaveBeenCalledWith({ answer: { answers: [{ selected: ["This week"] }] } });
});

test("a single question is compact: no steps, no Next, and Answer sends it", async () => {
  const screen = await render(<Questions request={asking(WEEK)} onAnswer={sent()} />);
  expect(screen.getByRole("button", { name: "Next" }).elements()).toHaveLength(0);
  expect(screen.getByText(/of 1/).elements()).toHaveLength(0);
  await expect.element(screen.getByRole("button", { name: "Answer" })).toBeVisible();
});

test("stepped, Back keeps the answers, the dots fill as questions are answered, and the focus lands on each step's words", async () => {
  const screen = await render(<Questions request={asking(WEEK, TOPICS)} onAnswer={sent()} />);
  const dots = () =>
    [
      ...(screen.container.querySelectorAll("[aria-hidden] > .size-1\\.5") as NodeListOf<Element>),
    ].map((dot) => getComputedStyle(dot).backgroundColor === token("accent"));
  expect(dots()).toEqual([false, false]);
  await screen.getByRole("radio", { name: "This week" }).click();
  expect(dots()).toEqual([true, false]);
  await screen.getByRole("button", { name: "Next" }).click();
  await expect.element(screen.getByText("What should the notes cover?")).toHaveFocus();
  await screen.getByRole("checkbox", { name: "Agenda" }).click();
  expect(dots()).toEqual([true, true]);
  await screen.getByRole("button", { name: "Back" }).click();
  await expect.element(screen.getByText("Which week?")).toHaveFocus();
  await expect.element(screen.getByRole("radio", { name: "This week" })).toBeChecked();
  await screen.getByRole("button", { name: "Next" }).click();
  await expect.element(screen.getByRole("checkbox", { name: "Agenda" })).toBeChecked();
});

test("the review's Change goes back to that question, and a failed send keeps every answer on the review", async () => {
  const screen = await render(
    <Questions request={asking(WEEK, TOPICS)} focus={false} onAnswer={sent("closed")} />,
  );
  await screen.getByRole("radio", { name: "This week" }).click();
  await screen.getByRole("button", { name: "Next" }).click();
  await screen.getByRole("checkbox", { name: "Agenda" }).click();
  await screen.getByRole("button", { name: "Next" }).click();
  await screen.getByRole("button", { name: "Change Week" }).click();
  await expect.element(screen.getByText("1 of 2")).toBeVisible();
  await expect.element(screen.getByRole("radio", { name: "This week" })).toBeChecked();
  await screen.getByRole("button", { name: "Next" }).click();
  await screen.getByRole("button", { name: "Next" }).click();
  await screen.getByRole("button", { name: "Answer" }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("That wasn't sent: the connection closed.");
  await expect.element(screen.getByText("Review your answers")).toBeVisible();
  await expect.element(screen.getByText("This week")).toBeVisible();
  await expect.element(screen.getByText("Agenda")).toBeVisible();
  await expect.element(screen.getByRole("button", { name: "Answer" })).toBeEnabled();
});

test("the arrow keys step where the focus isn't in an option, and Enter goes on", async () => {
  const screen = await render(<Questions request={asking(WEEK, TOPICS)} onAnswer={sent()} />);
  await screen.getByRole("radio", { name: "This week" }).click();
  (screen.getByText("Which week?").element() as HTMLElement).focus();
  await userEvent.keyboard("{ArrowRight}");
  await expect.element(screen.getByText("2 of 2")).toBeVisible();
  await userEvent.keyboard("{ArrowLeft}");
  await expect.element(screen.getByText("1 of 2")).toBeVisible();
  // In a radio group the arrows are the group's own: the step stays.
  await screen.getByRole("radio", { name: "This week" }).click();
  await userEvent.keyboard("{ArrowRight}");
  await expect.element(screen.getByText("1 of 2")).toBeVisible();
  // Enter in a field goes on, as a form's Enter does.
  await screen.getByRole("radio", { name: "Other" }).click();
  await screen.getByRole("textbox", { name: "Your answer" }).fill("Later");
  await userEvent.keyboard("{Enter}");
  await expect.element(screen.getByText("2 of 2")).toBeVisible();
});
