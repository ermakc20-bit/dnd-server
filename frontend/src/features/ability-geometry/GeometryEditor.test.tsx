import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { CardEditor } from "../cards/CardEditor";
import { blankCard } from "../cards/types";

it("configures native ability geometry and saves the existing card without JSON",async()=>{
  const save=vi.fn().mockResolvedValue(undefined);
  const initial={...blankCard(),name:"Mage",abilities:[{id:"a",schema_version:1 as const,name:"Area",description:"",
    action_type:null,uses:null,geometry:null,automation:null,visibility:"everyone" as const}]};
  render(<CardEditor initial={initial} disabled={false} players={[]} onLoadPlayers={vi.fn()}
    onSave={save} onCancel={vi.fn()}/>);
  fireEvent.click(screen.getByRole("button", { name: "Навыки, инвентарь и способности" }));
  fireEvent.click(screen.getByLabelText("Геометрия способности 1"));
  fireEvent.change(screen.getByLabelText("Форма области 1"),{target:{value:"cone"}});
  fireEvent.change(screen.getByLabelText("Источник области 1"),{target:{value:"point"}});
  fireEvent.change(screen.getByLabelText("Длина области 1"),{target:{value:"30"}});
  fireEvent.change(screen.getByLabelText("Угол области 1"),{target:{value:"90"}});
  fireEvent.change(screen.getByLabelText("Дальность (справочно) 1"),{target:{value:"0"}});
  fireEvent.change(screen.getByLabelText("Единицы области 1"),{target:{value:"метр"}});
  fireEvent.change(screen.getByLabelText("Цвет области 1"),{target:{value:"#ff7448"}});
  fireEvent.click(screen.getByRole("button",{name:"Сохранить карточку"}));
  await waitFor(()=>expect(save).toHaveBeenCalledTimes(1));
  expect(save.mock.calls[0][0]).toMatchObject({name:"Mage",abilities:[{name:"Area",automation:null,
    geometry:{shape:"cone",origin:"point",length:30,angle:90,range:0,units:"метр",color:"#ff7448"}}]});
});
