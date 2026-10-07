# HW5 — AI Prompts Log

Prompts written by Fran, recorded verbatim and grouped by problem.

## Setup

> now we will work at hw5

> create ai_prompts.md. we will update it while we work, with the lof of what i've written for you (prompts). i will give you for each problem the problem number and title, and you'll keep it on my words. if i write one or more follow-up prompts, you must accomodate on the related problem

## Prework — Problem 1

> i will describe for you, before starting, what we will do
>
> you are the agentic team that runs my shop, that sell yale stuff for students and parents (campus customs). we will build 3 pieces that are linked: an mcp server, a fastapi backend (with a multi agent team), and a react dash that make the human able to watch the agents' work and approve requests needed.
>
> Our team agent will have full connectivity - any agent can delegate tasks to others, when help is needed. We will build 5 agents:
> Boss - read each task (ticket), delegate them, and make final calls
> Inventory - check stock (SKU and size), spots shortfalls, and decide which seller will restock
> Accounting - watches cash and invoices, check margins, and prepare anything needed to make payments and purchase orders (they will be submitted to human approval)
> Facilities - watches shop space side
> Customer Service - draft msgs that to customers
>
> Our data is here: https://zlisto.github.io/mgt_409_fa26/data/hw5/data.zip. you must download and unzip this data, that contains original shop database. This db must be uploaded by the tools while tickets are solved. In order to preserve the original db, make a copy called data/campus_customs_new.db and the MCP server and backend will be linked to this copy. The original must be preserved to be audit or in case we need to restart out job.
>
> RULES
>
> * The field desk.date_today is "today" for our store. Use this date to understand what is delayed.
> * Vendor lead time is on vendors table
> * A vendor will not deliver a new product while the invoice is still unpaid
> * Human approval is required for any payment. YOU CANT MAKE ANY PAYMENT WITHOUT HUMAN APPROVAL. Since the payment is made, update the relevant table. DONT LET US CHARGE A CLIENT WHO HAS ALREADY PAID OR NOT TO SHIP A PRODUCT BECAUSE THE PAYMENT IS WRONGLY OPENED YET
> * If we dont have cash enough to a payment, the pay tool must refuse. WE CANT BE NEGATIVE. MAKE IT CLEAR THAT THE PAYMENT WAS REFUSED BECAUSE WE DONT HAVE FUNDS.
> * We dont have any source of entries. Money only goes out in this case.
> * Before a full run to resolve all tickets, make sure that we have RESET the database to the original values.
> * DO NOT EMAIL customers or call real vendors. FROM THIS TOOL WE ONLY NEED DRAFT.
>
>
> We will use PORTKEY_API_KEY. NO MATHER WHICH MODEL I TOLD YOU SHOULD BE DEFAULT, YOU MUST USE ONLY GPT-6-LUNA GIVEN THE COMPLEXITY OF THIS TASK. BEFORE ANY RUN, MAKE SURE YOU ARE USING THIS MODEL.

## Problem 2 — Study the campus customs database

> open data/campus_customs.db and make the copy i told you (campus_customs_new.db). study the three open tickets, and show me them too.
>
> start output/harness.md and for each table list the fields and one short line on why that table makes sense for our agent. be short. this harness will be fed while we walk through our 11 problems.

## Problem 3 — Build the MCP server

> white an mcp server in mcp_server/ using fastmcp. it will loinked to data/campus_customs_new.db. WE WILL CONNECT THEM LATER.
>
> Every agent in this homework will use tools contained in this MCP server (WE MUST BE ABLE TO ADD MORE TOOLS HERE LATER).
>
> WRITE THE FIRST 3 TOOLS. ALL OF THEM ARE NEEDED TO SOLVE THE TICKETS IN THE DB. NAME THEM IN AN INTUITIVE WAY. DONT INVENT ANY DATA. USE THE DATABASE.
>
> Update harness.md listing the three tools, including for each toolwhich table it reads, which ticket it help to solve (101, 102, or 103) and one short sentence telling why thats tool is the most useful for that ticket
>
> ADD a short file to mcp_server/README.md explaining what is the purpose of that MCP server, which db file it uses and the 3 tools you have just put on it.

## Problem 4 — Add the MCP server to the vibe coder and test each tool

> problem 4 - add the mcp server to vibe coder and test each tool

> is the mcp server in this project?

> do whatever is needed to connect through the .mcp.json

> how do i started my claude? just close and open again?

> is it connected now?

> how to open a new session?

> 1. Make sure the folder is `C:\Users\franc\Desktop\MBA\Ai foundation`. If it shows a different one, change it before you send your first message.
> 2. Send a first message such as "is the campus-customs MCP connected?"
> 3. If a prompt asks you to approve the `campus-customs` server from `.mcp.json`, click Allow or Approve.

> Tool loaded.

> do you remember everything we have to do about ai_prompts.d?

> okay but now we are working at hw5

> we are wroking in the problem 4 now, yes.
>
> test each of the 3 mcp tools you created and save the evidence in output/mcp_smoke.json showing for every tool the prompt that made it, the name and the tool output, that must match values in data/campus_customs_new.db

> Tool loaded.

## Problem 5 — Build the agent team and grow the MCP tools

> problem 5 - build the agent team and grow the mcp tools
>
> build the team (with the 5 personas) using pydanticAI, according to what i gave you on problem 1
> add to this my personal touch: the boss must be someone who wants to share as equal as possible the tasks, and who prioritize quality over quantity/time
> the inventory agent must pay deep attention to details, and be someone very handson
> the accounting must be very ethical
> the facilities must be very good on dealing with multi tasks
> the customer service must be very sensitive to very different types of public
>
> include prompts, modls, and agent loops to make them able to work together fully connected
>
> the prompts must be located in backend/prompts/, with one file per agent (5 in total). Data types go to backend/models.py, agent files under backend/.
>
> Remember to use my portkey_aí_key and ONLY GPT-6-LUNA for every agent. MAKE IT CLEAR FOR ME WHICH GPT MODEL YOU ARE USING.

## Problem 6 — Plan the three tickets

> problem 6 - plan the three tickets
> write what you expect the team do on each open ticket. make it short but clear and complete. build output/desk_tickets.html, a page that we can double-click containing one tab per ticket (overall 3 tabs). add two tabs mroe (overall 5 tabs), one for cash and one for reflections, that is gonna be filled later (write on them "fran will work here soon" just to check)
>
> on each ticket tab(first 3) fill an expected section and at the end an "actual" section that will be filled when we run the agents.
>
>
> THE EXPECTED SECTION must contain who the boss should call first, why, all the agent delegations you expect (be more specific than "boss call everyone", it would be inefficient) and whoch mcp tools you expect that run to use.
>
> YOU CANT SEND ALL THE SPECIALIST TO SOLVE EVERY TICKET. YOU MUST BE EFFICIENT AND USE ONLY THE NUMBER OF SPECIALIST NEEDED FOR EACH TICKET.

## Problem 7 — Backend routes

> problem 7 - backend routes
>
> the backend will be made at backend/main.py using fastapi and adding routes that:
>
> * return the 3 tickets and their status (open/resolved)
> * take a ticket id and run the team responsible for that
> * return recent agents event - what each agent said and which tools they used - in order to refresh the board
> * approve a payment or purchase after a human clicks approve (agents had prepared the payment, but this route is what made the cash changes)
> * return the current checking balance from cash_accounts
> * reset the database to the original when i want to run everything again
>
>
> from the backend/ folder, start the server with uvicorn main:app --reload --port 800
>
> in order to turn my backend at http://localhost:8000, enabling my frontend dashboard to call those routes
>
> at the end, update output/harness.md, including one line listing each rout (what is the url and what it does)

## Problem 8 — Agent dashboard

> problem 8 - agent dashboard
>
> build the frontend dashboard at frontend/ with react, vite and typescript. this page will call the routes built on the last problem.
>
> it MUST contain
>
> * all 3 tickets
> * a menu where you choose a ticket and 'play' buttom to start the agent team working on it
> * a list of each agent and what they are saying and doing while ticket runs (make it as short as possible), in case we have many agents working at the same time
> * a flag showing that a ticket is resolved when the run is finished
> * a short summary with what each agent did on tha tticket
> * the section where human approve payments and purchases when needed. if you need a payment/purchase be made but you dont have enough money, make it clear here and not approve the paument/purchase!
> * a clear checking balance, that MUST drop after an approved payment

> problem 8 - agent dashboard
> build the frontend dashboard at frontend/ with react, vite and typescript. this page will call the routes built on the last problem.
> it MUST contain
>
> * all 3 tickets
> * a menu where you choose a ticket and 'play' buttom to start the agent team working on it
> * a list of each agent and what they are saying and doing while ticket runs (make it as short as possible), in case we have many agents working at the same time
> * a flag showing that a ticket is resolved when the run is finished
> * a short summary with what each agent did on tha tticket
> * the section where human approve payments and purchases when needed. if you need a payment/purchase be made but you dont have enough money, make it clear here and not approve the paument/purchase!
> * a clear checking balance, that MUST drop after an approved payment
>
> this front end make talk to the backend at http://localhost:8000. on the backend, it is allowed the vite page origin (usually http://localhost:5173) in order to enable the browser to call these routs.
>
> start the board with npm run dev, openin the react desk in my browser
>
> write output/design.md, that will be filled later. make it blank.
>
> for now, i need to see functionalities. later, i will give it some more personality

> please stop everything and reset database

> i need some changes:
>
> 1. when i run you said "run #101: done". not, it is not. it is doing!
> 2. add an estimative of time or any other measure, and keep updating it to see how much it took and how much it lasts to finish
> 3. 2 tickets that were resolved are showing "db_status: waiting_approval". fix it.
> 4. make the webpage looks like an yale website, using bleu and white. inspire yourself on this website: https://som.yale.edu/programs/mba
> 5. w edont need "all agents run on gpt-6-luna. backend connected"
> 6. try to estimate for each run how many tokens were used and how much did it cost under the gpt-6-luna model. IT CANT BE DEDUCTED FROM CHECKIN BALANCE, it is only to accountability purposes.
> 7. exclude "db status" from the rectangle card for the problem
> 8. everytime you need a purchased be approved, release a block banner asking for approval. YOU MUST let me know you are waiting for me. I CAN CLICK ON IT TO APPROVE, NOT TO APPROVE, OR CLOSE, but it must block my screen if i dont do anything. IF I CANT PAY BECAUSE I DONT HAVE ENOUGH CASH, LET ME KNOW ON THIS BANNER, DEACTIVATE THE OPTION OF PAY AND ONLY LET ME DECLINE THE PAYMENT. if a new payment appears while i havent approved the first one, add a new layer, in a way that i will have 2 banners.
> 9. add a drop menu above the checking balance where i can verify the transactions that decreased me checking balance, starting from my initial amount
> 10. if there is a purchase made that is not being paid in cash now, add a section called accounts payable with when i will pay this purchase and how much it is, and how much is my projected saving if i dont receive any additional money
> 11. I must be able to stop a ticket and reset database anytime. (2 different optionS)

> add to output/design.md exactly this text:
>
> i need some changes:
>
> 1. fix status above the card: it was saying "done" while the card was still "running"
> 2. estimated time: make it more predictable for users
> 3. fix db_status: showing "resolved" instead of 2 tickets that were resolved are showing "db_status: waiting_approval". fix it.
> 4. make the webpage looks like an yale website, using bleu and white. inspire yourself on this website: https://som.yale.edu/programs/mba
> 5. w edont need "all agents run on gpt-6-luna. backend connected"
> 6. try to estimate for each run how many tokens were used and how much did it cost under the gpt-6-luna model. IT CANT BE DEDUCTED FROM CHECKIN BALANCE, it is only to accountability purposes.
> 7. exclude "db status" from the rectangle card for the problem
> 8. everytime you need a purchased be approved, release a block banner asking for approval. YOU MUST let me know you are waiting for me. I CAN CLICK ON IT TO APPROVE, NOT TO APPROVE, OR CLOSE, but it must block my screen if i dont do anything. IF I CANT PAY BECAUSE I DONT HAVE ENOUGH CASH, LET ME KNOW ON THIS BANNER, DEACTIVATE THE OPTION OF PAY AND ONLY LET ME DECLINE THE PAYMENT. if a new payment appears while i havent approved the first one, add a new layer, in a way that i will have 2 banners.
> 9. add a drop menu above the checking balance where i can verify the transactions that decreased me checking balance, starting from my initial amount
> 10. if there is a purchase made that is not being paid in cash now, add a section called accounts payable with when i will pay this purchase and how much it is, and how much is my projected saving if i dont receive any additional money
> 11. I must be able to stop a ticket and reset database anytime. (2 different optionS)

> add to output/design.md exactly this text:
>
> 1. fix status above the card: it was saying "done" while the card was still "running"
> 2. estimated time: make it more predictable for users
> 3. fix db_status: showing "resolved" instead of "waiting_approval"
> 4. consistency: make the webpage looks like an yale website, inspired by https://som.yale.edu/programs/mba
> 5. excluding unnecessary text: deleted "all agents run on gpt-6-luna. backend connected"
> 6. efficiency: included a estimative of tokens used and cost for each run and each ticket
> 7. excluding unnecessary text: deleted "db status" from cards
> 8. avoiding block for late approvals: added a block banner asking for approval
> 9. accountability: added a drop menu to verify the payments made
> 10. forecast: added a section of accounts payable for my purchases to be paid in the future
> 11. ownership: made it possible to stop a ticket and reset database anytime

## Problem 9 — Resolve the tickets

> problem 9 -  resolve the tickets
> reset the working database once again
> run all the tickets
> on output/desk_tickets.html made earlier, add to each table the text on the actual section, telling which agents worked, what they delegated, and which tools they used.
> dont delete or change the expected section
> on cash tab:
> start from checkin balance after run
> for each ticket add how cash changed when ticket was solved and why
> ending checking balance - MUST match cash_accounts
>
> save on outputs/
>
> resolved_tickets.json

## Problem 9 — Resolve the tickets

> problem 9 -  resolve the tickets
> reset the working database once again
> run all the tickets
> on output/desk_tickets.html made earlier, add to each table the text on the actual section, telling which agents worked, what they delegated, and which tools they used.
> dont delete or change the expected section
> on cash tab:
> start from checkin balance after run
> for each ticket add how cash changed when ticket was solved and why
> ending checking balance - MUST match cash_accounts
>
> save on outputs/
>
> resolved_tickets.json

> stop

> problem 9 -  resolve the tickets
> reset the working database once again
> run all the tickets
> on output/desk_tickets.html made earlier, add to each table the text on the actual section, telling which agents worked, what they delegated, and which tools they used.
> dont delete or change the expected section
> on cash tab:
> start from checkin balance after run
> for each ticket add how cash changed when ticket was solved and why
> ending checking balance - MUST match cash_accounts
>
> save on outputs/
>
> resolved_tickets.json
>
>  including for each ticket id, final status, short outcome, what each agent did, any human approval
> resolved_board.html a page i can double click to see a screenshot of my board for each ticket solved (overall 3 screenshots)
>
> append real runs to output/audit_trail.json
>
> append to output/harness.md anything needed to ensure it is covering tables, mcp tools, the 5 agents, api routes, dashboard, and safety rules

## Problem 10 — Reflection

> problem 10 - reflection
>
> add to reflection tab on desk_tickets.html considerations on this format
>
> base everything on the stuffs contained on this same html
>
> - Performance evaluation (for each ticket) - evaluate from 0 to 10 and tell why you gave each score
>
> - Compare and describe Expected vs Actual (for each ticket)
>
> - 3 ways you could simplify the agents work
>
> - 3 new problems these agent can solve
>
> - 3 new problems these agents couldn't solve
>
> be detailed and deep on the context

## Problem 11 — Organize and publish

> organize my files this way above. we will publish it to a PUBLIC github repository. DONT PUBLISH MY REAL .ENV. MAKE A PLACE HOLDER INSTEAD. DO NOT INCLUDE DATABASE THAT ARE UNDER data/
>
> this README file must explain copy original db to the working copy when you need a new run, start mcp server, start fastapi backend, start the react board, reset the db before a full three-ticket run.
>
> let me know if you ware missing any file/folder before submit to git

> 1 name is perfect, just add a -fas63 at the end
> 2 delete if they are not in the screenshot i sent you. my git structure must replicate the screenshot i sent.
> 3 ok

> ok run it
