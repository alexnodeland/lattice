/** A dashboard the tests and the screenshots share: one of every panel. */

import type { Dashboard } from "../artifactr-ui";

const WEEKS = ["Sep 22", "Sep 29", "Oct 6", "Oct 13"];

/** A support team's week: figures, a chart of each kind, a table, a note and a form. */
export const SUPPORT: Dashboard = {
  title: "Support this week",
  as_of: "2026-10-17T09:30:00Z",
  panels: [
    { type: "stat", label: "Open tickets", value: 42, change: -6 },
    { type: "stat", label: "First reply", value: 1.8, unit: "h", change: 0.3 },
    { type: "stat", label: "Solved on first reply", value: 64, unit: "%", change: 0 },
    { type: "stat", label: "On call", value: "Bob" },
    {
      type: "bar",
      label: "Tickets by channel",
      index: { key: "week", name: "Week" },
      series: [
        { key: "email", name: "Email" },
        { key: "chat", name: "Chat" },
        { key: "phone", name: "Phone" },
      ],
      rows: WEEKS.map((week, at) => ({
        week,
        email: 30 + at * 4,
        chat: 22 - at,
        phone: at === 2 ? null : 9 + (at % 2),
      })),
    },
    {
      type: "line",
      label: "Median first reply, hours",
      index: { key: "week", name: "Week" },
      series: [{ key: "reply", name: "First reply" }],
      rows: WEEKS.map((week, at) => ({ week, reply: [2.4, 2.1, 1.5, 1.8][at] ?? null })),
    },
    {
      type: "donut",
      label: "Open tickets by priority",
      parts: [
        { key: "low", name: "Low", value: 18 },
        { key: "normal", name: "Normal", value: 15 },
        { key: "high", name: "High", value: 6 },
        { key: "urgent", name: "Urgent", value: 2 },
        { key: "unset", name: "Unset", value: 1 },
      ],
    },
    {
      type: "table",
      label: "Longest open",
      columns: [
        { key: "ticket", name: "Ticket" },
        { key: "subject", name: "Subject" },
        { key: "days", name: "Days open" },
        { key: "vip", name: "Priority customer" },
      ],
      rows: [
        { ticket: "T-1042", subject: "Export stops at 10,000 rows", days: 12 },
        { ticket: "T-1077", subject: "SSO loop on the mobile app", days: 9 },
        { ticket: "T-1103", subject: "Invoice shows the wrong VAT", days: null },
        { ticket: "T-1120", subject: "Refund for a duplicate charge", days: 4, vip: true },
      ],
    },
    {
      type: "text",
      text: "**Notes.** Phone volume is **up** since the outage on Tuesday. <b>Raw HTML</b> stays text.",
    },
    { type: "form", form_id: "form_ack" },
  ],
};
