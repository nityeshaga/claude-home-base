# Brief: reviewer — design critic

**Inputs:** Screenshots of current designs of key pages, the design brief/aesthetic that was decided
**Output:** `review/design.md`.

The Design Critic agent's job is to improve the design. Use a Fable 5 subagent as a design critic.

Follow this procedure at each iteration:

- Ask it to evaluate the aesthetic that the design is going for, imagine how a top design studio would execute this aesthetic, then outline the biggest gaps

- Lastly, it should provide a score out of 10 indicating how close the current design is to that studio-level quality bar

Provide this guidance to the critic in its prompt:

- It should think high-level about the overall structure and composition as well as look at the fine details
- It should watch out for patterns that feel overdone, excessive, or otherwise obviously AI-generated, and penalize them
- It should provide tight, specific feedback, not vague prose
- It should be bold and opinionated, not rely on what’s safe or easy

