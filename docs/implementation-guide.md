# Implementation Guide

Start by adding `skills/resilience/SKILL.md` to the agent's system or skill layer. Then connect runtime detection if the host system supports middleware.

Production integrations should log activation signal, stress level, checkpoint result, selected recovery pattern, selected support action, and whether completion was verified.

Recommended integration order:

1. Detect resilience signals.
2. Select regulated response style.
3. Run the integrity checkpoint.
4. Select support action.
5. Plan recovery.
6. Evaluate completion.
