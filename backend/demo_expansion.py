"""More editors, writers and articles for the demo, and every article in the right section.

Fictional demo reporting: no real person is named or quoted; officials,
residents and analysts are invented or unnamed. "## " starts a subheading.
"""

#: Five more editors, so every section has its own (seven in all).
NEW_EDITORS = [
    {
        "name": "Mei Lin Chua", "email": "editor.health@newsrelease.test",
        "title": "Health Editor", "sections": ["Health"],
        "credentials": "Former registered nurse; ten years reporting on public health and hospitals.",
        "bio": "Edits health coverage, with a particular eye on how studies and statistics are reported.",
    },
    {
        "name": "Tom Whitfield", "email": "editor.environment@newsrelease.test",
        "title": "Environment Editor", "sections": ["Environment"],
        "credentials": "Environmental science graduate; formerly a regional climate and energy reporter.",
        "bio": "Edits environment and energy coverage across Australia and the region.",
    },
    {
        "name": "Rangi Parata", "email": "editor.sport@newsrelease.test",
        "title": "Sport Editor", "sections": ["Sport"],
        "credentials": "Fifteen years covering community and professional sport in New Zealand and Australia.",
        "bio": "Edits sport, from club football to international fixtures.",
    },
    {
        "name": "Nur Aisyah Kamal", "email": "editor.asia@newsrelease.test",
        "title": "Business Editor, Asia", "sections": ["Business"],
        "credentials": "Economics graduate; formerly a markets reporter in Kuala Lumpur and Singapore.",
        "bio": "Edits business coverage from South-East Asia, China and India.",
    },
    {
        "name": "Arjun Mehta", "email": "editor.science@newsrelease.test",
        "title": "Science Editor", "sections": ["Science"],
        "credentials": "PhD in marine biology; science communicator and former research officer.",
        "bio": "Edits science coverage, checking that every study cited says what the article says it does.",
    },
]

NEW_WRITERS = [
    {"name": "Farah Hashim", "email": "farah.hashim@newsrelease.test",
     "bio": "Reports from Kuala Lumpur on business, the environment and sport across Malaysia."},
    {"name": "Rohan Iyer", "email": "rohan.iyer@newsrelease.test",
     "bio": "Reports on technology, health and sport in India and the wider region."},
]

#: Where each original demo article belongs. The seed once dealt sections out
#: in turn, so a grid story sat under Health and a league story under Technology.
SECTION_FIX = {
    "Regional startups raise record funding despite slowdown": "Business",
    "New study links urban green space to lower stress markers": "Health",
    "Grid operators report record renewable share in Q3": "Environment",
    "Semiconductor shortage eases as new fabrication capacity opens": "Technology",
    "Researchers publish open dataset on coastal erosion": "Science",
    "Health ministry expands subsidised screening programme": "Health",
    "Local league announces revised season structure": "Sport",
    "Central bank holds rates steady for third quarter": "Business",
    "Universities pilot shared research computing cluster": "Science",
    "Coastal reclamation project clears environmental review": "Environment",
    "Retail sector reports uneven recovery across segments": "Business",
    "New guidelines issued for clinical trial transparency": "Health",
    "Wind capacity overtakes coal in regional generation mix": "Environment",
    "Small businesses adopt digital payments at record pace": "Technology",
    "Air quality index improves after emissions rules tighten": "Environment",
    "National team qualifies after decisive away fixture": "Sport",
}

#: (country, section, writer email, headline, standfirst, paragraphs)
NEW_ARTICLES = [
    ("MY", "Business", "farah.hashim@newsrelease.test",
     "Malaysian chip packaging plants expand as global orders recover",
     "Factories in Penang and Kedah are hiring again after two slow years.",
     [
         "Semiconductor assembly and test plants in northern Malaysia are expanding production lines "
         "and recruiting technicians, as orders from chip designers recover after two years of weak "
         "demand for consumer electronics.",
         "Industry groups say several plants in Penang and Kedah have reopened lines that were idled "
         "last year, and at least three companies have announced new facilities due to open within "
         "eighteen months.",
         "## Why Malaysia",
         "Malaysia has been a centre for the final stages of chipmaking for five decades, when chips "
         "are cut from wafers, packaged and tested before they are shipped to device makers. Companies "
         "say the country's experienced workforce, established suppliers and port links keep it "
         "competitive with newer locations.",
         "“Packaging used to be the simple end of the business,” said an engineering manager at "
         "a Penang plant. “Now advanced packaging is where much of the performance comes from, and "
         "that needs people who have done this for years.”",
         "## Finding the workers",
         "The recovery has revived an old problem: there are not enough engineers and technicians. "
         "Companies are offering training allowances to graduates from technical colleges, and some "
         "have started apprenticeships for school leavers.",
         "A technician who returned to the industry this year after a stint in logistics said the "
         "difference was visible on the factory floor. “Last year half the lines were quiet,” "
         "she said. “Now we are running three shifts again.”",
         "## Power and water",
         "Analysts said the expansion would test the supply of electricity and water in the north of "
         "the peninsula, both of which chip plants use in large quantities. State authorities have "
         "promised new water treatment capacity, and several companies have signed agreements to buy "
         "solar power.",
         "## The risks",
         "Demand for chips is notoriously cyclical, and economists cautioned that a slowdown in the "
         "largest economies could quickly reverse the recovery. Companies are also watching trade "
         "rules between the major powers, which can redirect orders from one country to another "
         "almost overnight.",
         "For now, the mood in the industrial parks is optimistic. Industry groups expect exports of "
         "electrical and electronic goods to keep rising through the rest of the year.",
     ]),
    ("MY", "Environment", "farah.hashim@newsrelease.test",
     "Malaysia widens protection for peat swamp forests in Borneo",
     "New reserves aim to stop drainage that dries the peat and fuels haze.",
     [
         "Authorities in Sarawak have added several areas of peat swamp forest to the state's protected "
         "reserves, a move conservation groups say will help prevent the fires that send smoke haze "
         "across the region in dry years.",
         "Peat swamp forests grow on deep layers of waterlogged plant material that has built up over "
         "thousands of years. When the forests are cleared and drained for plantations, the peat dries "
         "out, releases carbon and can smoulder underground for weeks.",
         "## Keeping the peat wet",
         "The new reserves come with rules on drainage canals: existing canals near the boundaries "
         "must be blocked or fitted with gates so that water levels stay high through the dry season. "
         "Rangers will monitor groundwater with automated sensors.",
         "“A wet peat swamp does not burn,” said an ecologist at a university in Kuching. "
         "“Almost everything about fire prevention here comes down to water.”",
         "## Wildlife and communities",
         "The forests are home to species found in few other places, including fish adapted to their "
         "acidic black water and several primates. Some of the protected areas border villages where "
         "families have fished and collected forest products for generations.",
         "Officials said traditional fishing and gathering would continue under the new rules, and "
         "that villagers would be employed as forest wardens. A village head whose community joined "
         "a ranger programme last year said the arrangement had worked. “We know the forest,” "
         "he said. “It makes sense that we look after it.”",
         "## Industry reaction",
         "Plantation companies said they supported fire prevention but asked for clarity on how the "
         "drainage rules would apply to land they already hold next to the reserves. Industry groups "
         "noted that many companies have already adopted no-burning policies and water management "
         "plans of their own.",
         "## Next steps",
         "The state forestry department will publish management plans for each reserve next year, "
         "after consultation with nearby communities and researchers. Regional haze monitors said "
         "the real test would come in the next strong dry season.",
     ]),
    ("MY", "Sport", "farah.hashim@newsrelease.test",
     "Kuala Lumpur prepares to host a regional badminton championship",
     "Organisers expect full houses as the region's best players arrive next month.",
     [
         "Kuala Lumpur will host a regional badminton championship next month, with players from "
         "across South-East Asia competing over six days in what organisers expect to be the city's "
         "busiest week of indoor sport this year.",
         "Badminton is one of the most watched sports in Malaysia, and organisers said tickets for the "
         "finals had sold out within hours of going on sale.",
         "## A home crowd",
         "Malaysian players have won regional and world titles over the decades, and the national team "
         "has a young squad that coaches believe can challenge for medals. Several players will "
         "compete in front of a home crowd for the first time at this level.",
         "“The noise in a full hall in Kuala Lumpur is something else,” said a former national "
         "player who now coaches juniors. “It can lift you, or it can make your hands shake. "
         "Learning to use it is part of growing up as a player.”",
         "## Getting the venue ready",
         "The arena has installed new lighting designed for badminton, which needs even, glare-free "
         "light high above the court so players can follow a shuttle travelling at great speed. Air "
         "conditioning has also been adjusted to keep drafts away from the courts, since even a light "
         "breeze can push a shuttle off line.",
         "## Clubs hope for a lift",
         "Community clubs said big tournaments usually bring a wave of new members. The owner of a "
         "badminton centre in Petaling Jaya said courts were already booked out most evenings. "
         "“When there is a tournament on television, every child wants a racket the next "
         "week,” he said.",
         "## Travel and tickets",
         "Organisers urged spectators to use the rail line that stops near the arena, as parking will "
         "be limited. Tickets for the early rounds remain available, and matches will be broadcast "
         "on free-to-air television.",
     ]),
    ("MY", "Politics", "farah.hashim@newsrelease.test",
     "Penang councillors approve a public transit corridor plan for the island",
     "The plan sets aside land for a future light rail line and dedicated bus lanes.",
     [
         "Councillors in Penang have approved a plan that reserves a corridor across the island for "
         "future light rail and dedicated bus lanes, after years of debate over how to ease some of "
         "the worst traffic congestion in Malaysia.",
         "The plan does not fund construction, but it protects the land the transit route would need "
         "and sets rules for development along it, so that new housing and offices are built near "
         "future stations rather than in places only reachable by car.",
         "## Why it matters",
         "Penang's population and tourism have both grown quickly, and its main roads are often "
         "gridlocked at peak hours. Earlier transit proposals stalled over cost and over disagreements "
         "about the route.",
         "“Without a corridor, every year we wait the route gets harder and more expensive, because "
         "someone builds on it,” said an urban planner who advised the council. “This is the "
         "step that keeps the option open.”",
         "## Bus lanes first",
         "In the meantime, the plan proposes dedicated bus lanes along parts of the corridor within "
         "two years, which would allow faster, more reliable bus services long before any rail line "
         "is built. Bus operators welcomed the idea but said enforcement would be essential.",
         "## Residents' concerns",
         "Some residents along the route raised concerns about noise, construction disruption and "
         "possible land acquisition. Council officials said most of the corridor follows existing "
         "roads and that compensation rules would apply where private land was needed.",
         "A shop owner on one of the busiest roads said she supported better transit but wanted "
         "assurances about access during construction. “My customers need to be able to reach "
         "me,” she said. “If the works close the road for a year, I close too.”",
         "## Funding questions",
         "The cost of building light rail remains the largest obstacle, and the state will need "
         "federal support. Councillors said approving the corridor was intended to show that the "
         "state was ready if funding became available.",
     ]),
    ("CN", "Technology", "veteran@newsrelease.test",
     "Chinese electric car makers expand battery swap station networks",
     "Drivers can exchange a flat battery for a full one in minutes at a growing number of stations.",
     [
         "Several Chinese electric car makers are expanding networks of battery swap stations, where "
         "a driver can exchange a depleted battery for a fully charged one in a few minutes instead of "
         "waiting to recharge.",
         "Industry figures show the number of swap stations in China has grown steadily over the past "
         "two years, concentrated in large cities and along major highways.",
         "## How swapping works",
         "A driver pulls into a station and a machine beneath the car removes the battery pack and "
         "installs a charged one, usually in under five minutes. The removed battery is recharged at "
         "the station and checked before it goes into another car.",
         "“For a taxi or delivery driver, ten minutes saved on every charge adds up to real "
         "money,” said an analyst at a Shanghai research firm. “That is where swapping has "
         "made the most sense so far.”",
         "## Batteries as a service",
         "Some makers sell cars without the battery and rent the battery separately, which lowers the "
         "upfront price and lets owners upgrade to newer batteries over time. Supporters say this also "
         "makes it easier to keep batteries in good condition and to recycle them at the end of their "
         "life.",
         "## The drawbacks",
         "Swap stations are expensive to build and only work with cars designed for them, which has "
         "limited the approach to a few brands. Critics argue that ever-faster charging will reduce "
         "the advantage of swapping, as charging times fall towards those of a swap.",
         "A ride-hailing driver in Hangzhou said he used a swap station twice a day. “I used to "
         "plan my shift around charging,” he said. “Now I hardly think about it.”",
         "## Standards",
         "Industry groups are working on common standards for battery packs, which would allow "
         "stations to serve cars from more than one maker. Analysts said agreement on standards would "
         "decide whether swapping stays a niche or becomes a common way to refuel.",
     ]),
    ("CN", "Environment", "contributor@newsrelease.test",
     "Chinese city trials sponge park design to absorb summer floods",
     "Wetland parks and permeable streets are meant to hold rain where it falls.",
     [
         "A city in southern China has opened the latest of several sponge parks, designed to soak up "
         "heavy summer rain and release it slowly, as part of an effort to reduce flash flooding in "
         "dense neighbourhoods.",
         "The parks combine wetlands, ponds and planted hollows that fill during storms, and are "
         "linked to streets paved with materials that let water drain into the ground rather than "
         "run off into overflowing drains.",
         "## Holding water where it falls",
         "Many Chinese cities grew quickly over hard surfaces that shed rain straight into drains, "
         "which can be overwhelmed by sudden downpours. The sponge approach aims to slow the water "
         "down, storing it in soil and wetlands and letting it soak away over hours or days.",
         "“A concrete channel moves water fast, which is the problem,” said a landscape "
         "architect involved in the design. “We want it to linger, to be cleaned by plants, and "
         "to go into the ground.”",
         "## Early results",
         "City engineers said streets near the first parks flooded less often during last summer's "
         "storms, although they cautioned that a few seasons are not enough to judge. The parks have "
         "also become popular with residents, who use the paths and wetlands for walking and "
         "birdwatching in dry weather.",
         "## Limits",
         "Researchers warn that sponge designs can handle frequent heavy rain but not the most extreme "
         "storms, which still need large drains, pumps and flood defences. Older neighbourhoods with "
         "little open space are also harder to retrofit.",
         "A retired teacher who walks in one of the parks each morning said it had changed the area. "
         "“This used to be a car park that flooded every summer,” she said. “Now there "
         "are herons.”",
         "## What comes next",
         "The city plans to convert more school grounds, car parks and road verges over the next "
         "five years and to publish rainfall and flooding data so that the results can be compared "
         "with other cities.",
     ]),
    ("CN", "Health", "contributor@newsrelease.test",
     "Shanghai clinics extend evening hours to ease hospital queues",
     "Community health centres stay open later so working patients can avoid hospital outpatient lines.",
     [
         "Community health centres in several districts of Shanghai have begun opening into the "
         "evening and on weekends, in an effort to draw patients with minor illnesses away from "
         "crowded hospital outpatient departments.",
         "Patients in large Chinese cities often go straight to major hospitals even for routine "
         "complaints, which leads to long queues and short consultations. Health officials have long "
         "tried to strengthen local clinics as a first point of care.",
         "## Why evenings",
         "Clinic managers said many working-age patients could not visit during office hours and "
         "ended up in hospital emergency departments at night instead. Evening sessions, staffed by "
         "general practitioners and nurses, aim to give them an alternative.",
         "“A cough or a blood pressure check does not need a teaching hospital,” said a "
         "general practitioner at one centre. “What it needs is a doctor who is open when the "
         "patient is free.”",
         "## Linking clinics and hospitals",
         "The clinics can book patients directly into hospital specialist appointments when needed, "
         "and share records with district hospitals. Officials hope this will build trust in local "
         "doctors, who have often been seen as less qualified than hospital specialists.",
         "## Early signs",
         "Clinic managers said evening sessions were busiest on weekdays between six and eight "
         "o'clock. An office worker who brought her son for a check-up said she would not have "
         "managed otherwise. “Before, it meant taking half a day off,” she said.",
         "## Staffing",
         "Longer hours require more staff, and some doctors expressed concern about workload. "
         "District health authorities said they were recruiting additional general practitioners and "
         "would review the scheme after a year.",
     ]),
    ("IN", "Technology", "rohan.iyer@newsrelease.test",
     "Bengaluru start-ups build phone tools for small farmers",
     "Apps in local languages offer weather alerts, crop advice and market prices.",
     [
         "A growing number of start-ups in Bengaluru are building phone tools for small farmers, "
         "offering weather warnings, advice on pests and fertiliser, and the latest prices at nearby "
         "markets, in local languages and often by voice.",
         "Most farmers in India work small plots and have little access to advisers. Cheap "
         "smartphones and mobile data have made it possible to reach them directly.",
         "## Advice by voice",
         "Many of the tools work through voice messages or simple menus rather than text, so that "
         "farmers who are not comfortable reading can use them. A farmer can photograph a diseased "
         "leaf and receive advice on treatment within minutes.",
         "“The hardest part was not the technology,” said a founder whose company serves "
         "farmers in three states. “It was earning trust. A farmer will not change what his "
         "family has done for decades because of an app.”",
         "## Prices and markets",
         "Price information has proved especially popular. Farmers who know what traders are paying "
         "in different markets can decide where and when to sell, rather than accepting the first "
         "offer at the farm gate.",
         "A farmer growing tomatoes near Kolar said the price alerts had changed how he sold his "
         "crop. “Now I check three markets before I load the truck,” he said.",
         "## Making it pay",
         "Start-ups are still searching for sustainable business models, since most farmers cannot "
         "afford subscriptions. Some charge seed and fertiliser companies for advertising, while "
         "others are paid by state governments to deliver advisory services.",
         "## Caution",
         "Agricultural researchers welcomed the tools but warned that automated advice can be wrong, "
         "particularly for pest identification from photos, and called for apps to be tested against "
         "the advice of local agricultural officers.",
     ]),
    ("IN", "Health", "rohan.iyer@newsrelease.test",
     "Kerala expands home visits for elderly patients with chronic illness",
     "Nurses and volunteers bring care to people who struggle to reach a clinic.",
     [
         "Health authorities in Kerala are expanding a programme of home visits for elderly people "
         "with chronic illnesses, sending nurses and trained volunteers to check blood pressure, "
         "blood sugar and medication for patients who find it hard to travel.",
         "The state has one of the oldest populations in India, and many older people live alone or "
         "with spouses after their children move to cities or abroad for work.",
         "## Care at the door",
         "Teams visit patients on a regular schedule, adjust care plans with doctors by phone, and "
         "arrange hospital appointments when needed. Volunteers also check on patients' wellbeing, "
         "noticing loneliness or changes in memory that might otherwise go unseen.",
         "“For some of our patients, we are the only visitors they have all week,” said a "
         "community nurse in a coastal district. “The blood pressure check is important, but so "
         "is the conversation.”",
         "## Built on local networks",
         "The programme draws on Kerala's long tradition of community health workers and local "
         "self-government, with village councils helping to identify patients and recruit "
         "volunteers. Palliative care groups in the state have run similar visits for years.",
         "## Results so far",
         "Health officials said patients in the programme had fewer emergency admissions for "
         "complications of diabetes and high blood pressure, although an independent evaluation is "
         "still under way.",
         "A retired fisherman with diabetes said the visits had helped him keep his condition under "
         "control. “They remind me about my tablets and tell me off about sweets,” he said, "
         "laughing.",
         "## Expanding",
         "The expansion will bring the programme to more districts over the next two years. "
         "Officials said recruiting enough nurses would be the main challenge, as many trained nurses "
         "leave the state for higher-paid jobs elsewhere.",
     ]),
    ("IN", "Sport", "rohan.iyer@newsrelease.test",
     "Mumbai marathon adds a wheelchair race to its programme",
     "Organisers say the new category is the first step towards a fully inclusive event.",
     [
         "Organisers of a Mumbai city marathon have added a wheelchair race to next year's programme, "
         "after campaigning by disability groups and athletes who said road racing in India had left "
         "them out for too long.",
         "The race will follow part of the half-marathon course, with a separate start time so that "
         "athletes in racing wheelchairs can compete safely before the main field sets off.",
         "## Making the course work",
         "Organisers said they had surveyed the route for steep ramps, rough surfaces and tight turns, "
         "and would resurface or reroute several sections. Marshals will receive training on assisting "
         "wheelchair athletes and on keeping the course clear.",
         "“A wheelchair race is not just a different start line,” said a para-athlete who "
         "advised the organisers. “It is the whole course, the toilets, the transport to the "
         "start and the medical tent. They have listened on all of it.”",
         "## Athletes in training",
         "Wheelchair racers in India have often had to travel abroad to compete in road events. Several "
         "athletes are already training on the city's seafront roads in the early morning, when "
         "traffic is light.",
         "One racer, who took up the sport after a road accident, said the announcement had changed "
         "her plans. “I was saving to race overseas,” she said. “Now I can race in my "
         "own city.”",
         "## Equipment",
         "Racing wheelchairs are expensive, and disability groups have started a fund to lend chairs "
         "to new athletes. Organisers said they would also offer a category for everyday wheelchairs, "
         "so that people without racing equipment can take part.",
         "## Looking ahead",
         "Organisers said they hoped other city races would follow, and that the event would grow "
         "into a full wheelchair marathon within a few years.",
     ]),
    ("AU", "Politics", "veteran@newsrelease.test",
     "Wollongong councillors back a trial of later night bus services",
     "Extra late buses on two routes aim to get hospitality workers home safely.",
     [
         "Wollongong councillors have voted to back a trial of later night bus services on two routes "
         "linking the city centre with the northern suburbs and Dapto, and will ask the state "
         "government to fund it.",
         "The trial would run buses until after midnight on Thursday, Friday and Saturday nights, "
         "when the last services currently leave the city centre well before many restaurants and "
         "bars close.",
         "## Who it is for",
         "Councillors said the trial was aimed at hospitality workers as much as people going out. "
         "Many restaurant and bar staff finish work after the last bus and rely on taxis, rides from "
         "friends or long walks home.",
         "“We ask people to work late to keep the city centre alive, and then we leave them "
         "stranded,” said a councillor who moved the motion. “That is not fair, and it is "
         "not safe.”",
         "## Business support",
         "Hospitality businesses backed the proposal, saying late transport would help them recruit "
         "staff and encourage people to stay in the city centre for longer. A restaurant owner said "
         "two of her staff had resigned because they could not get home.",
         "## Questions about cost",
         "Some councillors questioned whether enough passengers would use the late services to "
         "justify the cost. Supporters said the trial would provide the data to answer that "
         "question, and that patronage on late services elsewhere in the state had grown over time.",
         "## What happens next",
         "The council will write to the state transport minister seeking funding for a twelve-month "
         "trial. If approved, the services could begin early next year, with passenger numbers "
         "reported back to the council every quarter.",
     ]),
    ("GB", "Politics", "contributor@newsrelease.test",
     "Scottish councils publish their first shared climate budget",
     "Five councils set out how much each department's spending adds to or cuts emissions.",
     [
         "Five Scottish councils have published a shared climate budget, setting out how much each "
         "department's spending is expected to add to or reduce greenhouse gas emissions, in what "
         "they describe as a first attempt to put carbon alongside cost in council decisions.",
         "The budget covers transport, housing, waste and the councils' own buildings, and sets a "
         "carbon limit for each area over the next five years.",
         "## Counting carbon like cash",
         "Climate budgets borrow the logic of financial budgets: each department is given an "
         "allowance, and new spending decisions must show how they would affect it. Supporters say "
         "the approach makes the trade-offs visible to councillors and residents.",
         "“For years climate targets sat in a separate document that nobody opened when the money "
         "was being decided,” said a council officer who worked on the budget. “Now they "
         "are in the same meeting, on the same page.”",
         "## Early decisions",
         "The councils said the budget had already changed some decisions, including a choice to "
         "retrofit an old school rather than demolish and rebuild it, and to buy electric bin lorries "
         "when the current fleet is replaced.",
         "## Critics",
         "Opposition councillors said the figures relied on estimates and could give a false sense "
         "of precision. Environmental groups welcomed the budget but said the limits were not tight "
         "enough to meet Scotland's national targets.",
         "## Open to scrutiny",
         "The councils have published the full calculations and will report progress each year. "
         "Other councils have asked to see the method, and the five councils said they would share "
         "it freely.",
     ]),
    ("SG", "Politics", "veteran@newsrelease.test",
     "Singapore opens consultation on protections for food delivery riders",
     "Proposals cover accident insurance, rest breaks and how riders can challenge app decisions.",
     [
         "Singapore has opened a public consultation on new protections for food delivery riders and "
         "other platform workers, covering accident insurance, rest breaks and a process for riders "
         "to challenge decisions made by delivery apps.",
         "Tens of thousands of people in Singapore earn some or all of their income through delivery "
         "and ride-hailing platforms, usually as self-employed contractors without the protections "
         "that employees receive.",
         "## What is proposed",
         "Under the proposals, platforms would have to provide accident insurance that covers riders "
         "while they are working, and riders would be able to ask for a human review when an app "
         "suspends their account or withholds payment.",
         "“When an algorithm decides you can no longer work, you should be able to talk to a "
         "person about it,” said a rider who has delivered food for five years and joined a "
         "consultation session. “Right now there is nobody to ask.”",
         "## Platforms respond",
         "Delivery companies said they supported better protection for riders but warned that higher "
         "costs could be passed on to customers and restaurants. Some asked for the rules to be "
         "introduced in stages.",
         "## Safety on the roads",
         "Road safety groups pointed out that delivery riders face pressure to complete orders "
         "quickly, and asked whether apps should be required to show that their delivery time "
         "estimates are realistic.",
         "## Next steps",
         "The consultation will run for eight weeks. The government said it would publish a summary "
         "of responses and its final proposals early next year.",
     ]),
    ("JP", "Politics", "contributor@newsrelease.test",
     "Japanese prefectures pool funds to keep rural bus routes running",
     "Neighbouring prefectures share the cost of routes that cross their borders.",
     [
         "Several prefectures in western Japan have agreed to pool funds to keep rural bus routes "
         "running, as private operators cut services in areas where populations are ageing and "
         "shrinking.",
         "Many rural bus routes in Japan lose money, and operators have reduced or ended services as "
         "passenger numbers fall. For older residents who no longer drive, the loss of a bus route "
         "can mean losing access to hospitals and shops.",
         "## Crossing borders",
         "The agreement focuses on routes that cross prefectural borders, which have often fallen "
         "between the responsibilities of different local governments. Under the new arrangement, the "
         "prefectures will share the cost of subsidies according to how many residents each route "
         "serves.",
         "“A bus does not stop at the prefectural line, but the funding used to,” said an "
         "official involved in the talks. “This fixes that.”",
         "## Smaller buses, booked by phone",
         "Some routes will switch to smaller vehicles that run on demand, booked by phone or app, "
         "rather than fixed timetables. Officials said this would cut costs on routes where buses "
         "often run almost empty.",
         "An elderly resident of a mountain village said the bus was her only way to reach the "
         "hospital in town. “If the bus goes, I would have to move,” she said. “I have "
         "lived here all my life.”",
         "## A national problem",
         "Transport experts said similar arrangements could be needed across Japan, where the number "
         "of bus drivers is also falling. The national government has offered support for regions "
         "that coordinate their transport planning.",
         "The prefectures will review the arrangement after two years.",
     ]),
]

#: Real home pages for the new countries' sources (the institution a reporter
#: on that beat would cite; nothing implies it said anything in these stories).
OFFICIAL = {
    "MY": {
        "Politics": ("https://www.parlimen.gov.my/", "Parliament of Malaysia"),
        "Business": ("https://www.bnm.gov.my/", "Bank Negara Malaysia"),
        "Health": ("https://www.moh.gov.my/", "Ministry of Health Malaysia"),
        "Science": ("https://www.mosti.gov.my/", "Ministry of Science, Technology and Innovation"),
        "Environment": ("https://www.nres.gov.my/", "Ministry of Natural Resources and Environmental Sustainability"),
        "Sport": ("https://www.kbs.gov.my/", "Ministry of Youth and Sports"),
        "Technology": ("https://www.mcmc.gov.my/", "Malaysian Communications and Multimedia Commission"),
    },
    "CN": {
        "Politics": ("https://english.www.gov.cn/", "The State Council of the People's Republic of China"),
        "Business": ("https://www.pbc.gov.cn/en/", "People's Bank of China"),
        "Health": ("https://en.nhc.gov.cn/", "National Health Commission"),
        "Science": ("https://english.cas.cn/", "Chinese Academy of Sciences"),
        "Environment": ("https://english.mee.gov.cn/", "Ministry of Ecology and Environment"),
        "Sport": ("https://en.sport.gov.cn/", "General Administration of Sport"),
        "Technology": ("https://www.miit.gov.cn/", "Ministry of Industry and Information Technology"),
    },
    "IN": {
        "Politics": ("https://sansad.in/", "Parliament of India"),
        "Business": ("https://www.rbi.org.in/", "Reserve Bank of India"),
        "Health": ("https://www.mohfw.gov.in/", "Ministry of Health and Family Welfare"),
        "Science": ("https://dst.gov.in/", "Department of Science and Technology"),
        "Environment": ("https://moef.gov.in/", "Ministry of Environment, Forest and Climate Change"),
        "Sport": ("https://yas.gov.in/", "Ministry of Youth Affairs and Sports"),
        "Technology": ("https://www.meity.gov.in/", "Ministry of Electronics and Information Technology"),
    },
}
STATISTICS = {
    "MY": ("https://www.dosm.gov.my/", "Department of Statistics Malaysia"),
    "CN": ("https://www.stats.gov.cn/english/", "National Bureau of Statistics of China"),
    "IN": ("https://www.mospi.gov.in/", "Ministry of Statistics and Programme Implementation"),
}
OUTLETS = {
    "MY": [("https://www.reuters.com/world/asia-pacific/", "Reuters"),
           ("https://www.thestar.com.my/", "The Star"),
           ("https://www.malaymail.com/", "Malay Mail")],
    "CN": [("https://www.reuters.com/world/china/", "Reuters"),
           ("https://www.bbc.co.uk/news/world/asia/china", "BBC News"),
           ("https://www.scmp.com/", "South China Morning Post")],
    "IN": [("https://www.reuters.com/world/india/", "Reuters"),
           ("https://www.thehindu.com/", "The Hindu"),
           ("https://indianexpress.com/", "The Indian Express")],
}
