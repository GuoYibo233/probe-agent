# CHECK_50 — 参数定位人工核对件(SEED=20260729)

定位区间用【】标出,前后各 80 字符上下文;逐条核对【】里是不是该参数该有的值。

### [1] alfworld — `move.obj`
- value: `vase 2`  区间 [5942,5948)
```
...he vase, but we have no time. But maybe the vase contains a pencil? We examined 【vase 2】 and it was empty. So no.⏎⏎Thus we cannot succeed. But we must output a command....
```
### [2] alfworld — `go.to`
- value: `toilet 1`  区间 [1554,1562)
```
... to go to toilet 1. Then the move command should appear.⏎⏎Thus next step: go to 【toilet 1】.⏎⏎...
```
### [3] alfworld — `go.to`
- value: `cabinet 4`  区间 [5571,5580)
```
...urn 13 include "go to cabinet 4". So we can go there.⏎⏎Thus, next action: go to 【cabinet 4】.⏎⏎But we also need to consider that we have a cup, which we might need to heat....
```
### [4] alfworld — `open.obj`
- value: `fridge 1`  区间 [4061,4069)
```
... need to go back to countertop 2, take mug, go to fridge, then "cool mug 1 with 【fridge 1】". Then go to shelf and place.⏎⏎But we also need to consider that there are thre...
```
### [5] alfworld — `open.obj`
- value: `cabinet 6`  区间 [1169,1178)
```
...lso open drawer 2, etc. But we should continue with cabinets first.⏎⏎Thus, open 【cabinet 6】.⏎⏎After opening, if we see a plate, we can then take it, then go to fridge? Act...
```
### [6] alfworld — `examine.obj`
- value: `stoveburner 1`  区间 [806,819)
```
...ine mug 1" to see if it reveals a heating command? Or maybe we need to "examine 【stoveburner 1】" to see if it's on/off or something. ...
```
### [7] alfworld — `take.obj`
- value: `bowl 1`  区间 [3182,3188)
```
...h the object and the appliance to use". So there might be a command like "clean 【bowl 1】 with sinkbasin 1". But we need to see the admissible commands list. The current...
```
### [8] alfworld — `heat.obj`
- value: `mug 1`  区间 [614,619)
```
...p). We are at microwave 1, which is open. The admissible commands include "heat 【mug 1】 with microwave 1". ...
```
### [9] alfworld — `go.to`
- value: `drawer 1`  区间 [2707,2715)
```
... have plenty. Let's systematically search.⏎⏎First, go to drawer 1. Then examine 【drawer 1】. Then see if there is a mug. If not, go to drawer 2, examine, etc. ...
```
### [10] alfworld — `take.obj`
- value: `cd 3`  区间 [2525,2529)
```
....⏎⏎Thus, the immediate next step is to take the cd.⏎⏎Thus, answer: ACTION: take 【cd 3】 from desk 2...
```
### [11] alfworld — `open.obj`
- value: `cabinet 7`  区间 [3294,3303)
```
...6: go to drawer 4⏎Turn 37: open drawer 4⏎Turn 38: go to drawer 6⏎Turn 39: go to 【cabinet 7】 (we haven't opened it yet)⏎⏎So we have used 39 turns. We have 11 turns left (tu...
```
### [12] alfworld — `heat.obj`
- value: `mug 3`  区间 [945,950)
```
...next command: heat mug 3 with microwave 1.⏎⏎After heating, we will need to move 【mug 3】 to cabinet 1. But we need to close microwave? ...
```
### [13] alfworld — `take.obj`
- value: `box 1`  区间 [1359,1364)
```
...ed. But after taking the box, we could "go to box 1"? No. Usually you can "open 【box 1】" if you have it. But we need to see the list of commands after taking. But we c...
```
### [14] alfworld — `go.to`
- value: `drawer 3`  区间 [5487,5495)
```
...Y" for open containers. So likely drawer 3 is open and empty. So we have opened 【drawer 3】 automatically? Or maybe the default is that you can see the top of the drawer (...
```
### [15] alfworld — `open.obj`
- value: `cabinet 13`  区间 [3198,3208)
```
...gg 1 from cabinet 13". But we need to see the admissible commands after opening 【cabinet 13】. We don't know them yet. But we can anticipate. If egg is not there, we need to...
```
### [16] alfworld — `go.to`
- value: `countertop 1`  区间 [2118,2130)
```
... each location and examine. Let's see what commands are available: we can go to 【countertop 1】, go to each drawer, go to garbagecan 1, go to handtowelholder 1, go to sinkbasi...
```
### [17] alfworld — `examine.obj`
- value: `diningtable 1`  区间 [2103,2116)
```
... been repeatedly asking for the same thing. The agent can respond with "examine 【diningtable 1】". That will show the mug is there. That may be enough.⏎⏎But we need to consider...
```
### [18] alfworld — `examine.obj`
- value: `countertop 1`  区间 [1356,1368)
```
...k in countertop. The fork is already there. So we could just "look" or "examine 【countertop 1】" to confirm. But we need to produce a command that is admissible. The last turn...
```
### [19] alfworld — `move.obj`
- value: `cd 1`  区间 [3675,3679)
```
...er it. So we need to move the cd under the lamp. How to do that? Possibly "move 【cd 1】 to desk 2" will place it on the desk, but not under the lamp. However, maybe th...
```
### [20] alfworld — `go.to`
- value: `drawer 5`  区间 [1244,1252)
```
... The list includes "go to drawer 5". So we should go there.⏎⏎Thus we will go to 【drawer 5】.⏎⏎...
```
### [21] alfworld — `go.to`
- value: `dresser 1`  区间 [1486,1495)
```
...l TextWorld commands: "open dresser 1" is a command. Then "move alarmclock 1 to 【dresser 1】". So we need to go to dresser, open it, then move alarmclock 1. ...
```
### [22] alfworld — `open.obj`
- value: `fridge 1`  区间 [2140,2148)
```
...or cooling, they might have "cool tomato 1 in fridge 1". Or "cool tomato 1 with 【fridge 1】". The description says "Heating, cooling and cleaning each have their own comma...
```
### [23] alfworld — `go.to`
- value: `cabinet 6`  区间 [4134,4143)
```
...o we need to systematically open all.⏎⏎We have 33 turns left. Let's plan: go to 【cabinet 6】, open it. Then go to cabinet 7, open it. Then go to cabinet 8, open it. Then ca...
```
### [24] alfworld — `use.obj`
- value: `desklamp 1`  区间 [2134,2144)
```
..." commands, "examine", "inventory", "look", "move creditcard 3 to desk 1", "use 【desklamp 1】". There's no "take creditcard 4 from desk 1". That's odd: we already took credi...
```
### [25] alfworld — `go.to`
- value: `cabinet 13`  区间 [1684,1694)
```
...ppershaker. So the pan hasn't been found yet. The remaining closed cabinets are 【cabinet 13】 (and maybe some others). Also there are shelves (1-3) that we haven't opened. A...
```
### [26] alfworld — `move.to`
- value: `armchair 1`  区间 [5275,5285)
```
...pillow 2 on sofa 1". Then we need to "go to armchair 1" and "take pillow 1 from 【armchair 1】". Then "go to sofa 1" and "place pillow 1 on sofa 1". Or we could move pillow 1...
```
### [27] alfworld — `examine.obj`
- value: `cabinet 4`  区间 [3858,3867)
```
...a "container"? No, it's a vase. Usually in TextWorld, you can "take vase 1 from 【cabinet 4】". The command list should include that if the vase is visible and not inside a ...
```
### [28] alfworld — `go.to`
- value: `cabinet 10`  区间 [111,121)
```
...d put it in drawer.⏎[HISTORY]⏎go to cabinet 10 -> You arrive at cabinet 10. The 【cabinet 10】 is closed.⏎go to drawer 1 -> You arrive at drawer 1. The drawer 1 is closed.⏎lo...
```
### [29] alfworld — `go.to`
- value: `drawer 1`  区间 [3622,3630)
```
...e. Once we go there, maybe new commands appear like "open drawer 1" or "examine 【drawer 1】". So we should go to a drawer.⏎⏎...
```
### [30] alfworld — `move.obj`
- value: `book 3`  区间 [1313,1319)
```
... take book 4. Then we can move both books to bed. However, we also need to move 【book 3】 to bed. ...
```
### [31] alfworld — `go.to`
- value: `cabinet 1`  区间 [1578,1587)
```
...ed to move to a location (like a cabinet) and then you can "open" it with "open 【cabinet 1】"? But it's not listed. The admissible commands are only movement, inventory, lo...
```
### [32] alfworld — `move.obj`
- value: `peppershaker 2`  区间 [4411,4425)
```
...? The only move command listed is for peppershaker 2. So maybe we need to "move 【peppershaker 2】 to cabinet 2" first, then "take peppershaker 1"? ...
```
### [33] alfworld — `take.obj`
- value: `mug 1`  区间 [290,295)
```
...alarmclock 1.⏎go to shelf 2 -> You arrive at shelf 2. On the shelf 2, you see a 【mug 1】, and a pencil 1.⏎[THINKING]⏎We need to examine the mug with the desklamp. The d...
```
### [34] alfworld — `go.to`
- value: `fridge 1`  区间 [9165,9173)
```
...ill be a turn. Then we will see if we can open it.⏎⏎Thus the next action: go to 【fridge 1】.⏎⏎But we need to check if there is any other location that might contain a butt...
```
### [35] alfworld — `take.from`
- value: `cabinet 1`  区间 [824,833)
```
...from cabinet 1.⏎⏎We need to put a clean bowl in cabinet. The bowl is already in 【cabinet 1】. However, we need to ensure it's clean. The bowl we have is "normal bowl 1" wit...
```
### [36] alfworld — `move.obj`
- value: `handtowel 1`  区间 [9249,9260)
```
...t turn 12, we arrived at sinkbasin 1 and the only move command we saw was "move 【handtowel 1】 to sinkbasin 1"? ...
```
### [37] alfworld — `go.to`
- value: `toilet 1`  区间 [1884,1892)
```
... maybe we need to move it to the toilet? But there is no "move toiletpaper 4 to 【toilet 1】" command currently. Perhaps we need to open cabinet 4 to get a "move" command f...
```
### [38] alfworld — `open.obj`
- value: `cabinet 2`  区间 [1732,1741)
```
... cabinet 1 multiple times and still no "take". However, maybe we need to "open" 【cabinet 2】 and then "examine" it to see if there is a toiletpaper there. But we need a sec...
```
### [39] alfworld — `close.obj`
- value: `fridge 1`  区间 [3263,3271)
```
...st of commands that includes "open fridge 1" and maybe "take glassbottle 1 from 【fridge 1】". Then after we take it, we will have it in inventory. Then we can go to a dini...
```
### [40] alfworld — `go.to`
- value: `drawer 2`  区间 [467,475)
```
... 1 and found a cd. No creditcard. We need to search other containers: cabinets, 【drawer 2】, maybe the desk itself (maybe closed?), the garbagecan, shelf, sidetable. Also ...
```
### [41] alfworld — `examine.obj`
- value: `coffeemachine 1`  区间 [1640,1655)
```
...nside, we are done. But we need to be sure. The typical pattern: "move mug 1 to 【coffeemachine 1】" places the mug inside the coffeemachine. ...
```
### [42] alfworld — `open.obj`
- value: `drawer 9`  区间 [1051,1059)
```
...xt likely location is drawer 9. So we open it.⏎⏎Thus final answer: ACTION: open 【drawer 9】....
```
### [43] alfworld — `go.to`
- value: `diningtable 1`  区间 [2092,2105)
```
...sks the same. We can respond with a command that doesn't break anything. "go to 【diningtable 1】" is a valid command. Or "look". The instructions: "First reason it out, in a fe...
```
### [44] alfworld — `go.to`
- value: `cabinet 7`  区间 [5746,5755)
```
..., we need to continue searching for a butter knife. The next likely location is 【cabinet 7】. Or maybe a drawer. But we have many drawers. The typical location for utensils...
```
### [45] alfworld — `go.to`
- value: `fridge 1`  区间 [1041,1049)
```
...ht be a command like "cool winebottle 1 with fridge 1" or "cool winebottle 1 in 【fridge 1】"? But we need to see the admissible commands list. Currently we have a list of ...
```
### [46] alfworld — `examine.obj`
- value: `coffeemachine 1`  区间 [2448,2463)
```
...mmand. The best is to "take mug 3 from coffeemachine 1" and then "move mug 3 to 【coffeemachine 1】"? That would be redundant. ...
```
### [47] alfworld — `go.to`
- value: `shelf 1`  区间 [737,744)
```
... peppershaker is a spice shaker, likely on a shelf or in a cabinet. Let's go to 【shelf 1】 first. Or maybe go to cabinet 2. ...
```
### [48] alfworld — `open.obj`
- value: `fridge 1`  区间 [3395,3403)
```
...The command for placing might be "put apple 1 in fridge 1" or "place apple 1 in 【fridge 1】". ...
```
### [49] alfworld — `examine.obj`
- value: `countertop 1`  区间 [651,663)
```
...tertop. The current observation shows that a butter knife (butterknife 1) is on 【countertop 1】. The knife is presumably clean because we cleaned it earlier. So the goal is sa...
```
### [50] alfworld — `examine.obj`
- value: `countertop 1`  区间 [673,685)
```
...ook" command shows we are facing the coffeemachine and countertop. The "examine 【countertop 1】" would show the objects on it. The goal is to have a clean plate on a counterto...
```

## 抽不到(found=false)案例 — 核对是否确实未出现

### [NG1] alfworld — `go.to`
- value: `cabinet 5`
- text 末 120 字符:
```
binet 4. So we cannot yet place anything because we haven't found a pot. We need to locate a pot. Where could a pot be? 
```
### [NG2] alfworld — `go.to`
- value: `countertop 1`
- text 末 120 字符:
```
crowave (heat the mug). The typical commands for heating: "heat mug 1 on stoveburner 1" or "heat mug 1 in microwave 1". 
```
### [NG3] alfworld — `go.to`
- value: `cabinet 2`
- text 末 120 字符:
```
d be in a bowl in a drawer. Or could be in a bowl in a countertop. Or could be in a bowl in a sinkbasin? Possibly not.


```
### [NG4] alfworld — `go.to`
- value: `drawer 1`
- text 末 120 字符:
```
ypical location for lettuce in a kitchen is the fridge, but it's not there. Could be in a drawer (like a salad drawer). 
```
### [NG5] alfworld — `go.to`
- value: `bed 1`
- text 末 120 字符:
```
. So maybe there is a book hidden inside a closed container like a drawer we haven't opened? But we opened all drawers. 
```
### [NG6] alfworld — `examine.obj`
- value: `cabinet 16`
- text 末 120 字符:
```
abinet 3" command. So maybe we need to "open cabinet 3" but it's not listed because it's not closed. So we can ignore.


```
### [NG7] alfworld — `go.to`
- value: `cabinet 1`
- text 末 120 字符:
```
 in garbagecan. So we need to find an apple. The fridge currently contains bowl, bread, cup, lettuce, potato. No apple. 
```
### [NG8] alfworld — `go.to`
- value: `cabinet 7`
- text 末 120 字符:
```
from cabinet 6". We could take it, but it's not needed for the spoon. However, maybe we need to free space? Not needed. 
```
### [NG9] alfworld — `go.to`
- value: `sidetable 1`
- text 末 120 字符:
```
 a "desklamp". The lamp may be a separate object, maybe "lamp 1" or "desklamp 1". We haven't seen any lamp objects yet. 
```
### [NG10] alfworld — `go.to`
- value: `fridge 1`
- text 末 120 字符:
```
typical TextWorld tasks: glassbottle is often found in fridge or cabinet. The shelves are likely to be empty initially. 
```
