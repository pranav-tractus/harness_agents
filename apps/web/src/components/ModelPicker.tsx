import { useEffect, useState } from "react";
import { api, type ModelOption } from "@/api/client";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";

type Props = {
  value: string;
  onChange: (modelKey: string) => void;
};

export function ModelPicker({ value, onChange }: Props) {
  const [models, setModels] = useState<ModelOption[]>([]);

  useEffect(() => {
    api.listModels().then(setModels).catch(console.error);
  }, []);

  return (
    <div className="flex items-center gap-2">
      <Label htmlFor="model-picker">Model</Label>
      <Select value={value} onValueChange={(v) => v && onChange(v)}>
        <SelectTrigger id="model-picker" className="w-[220px]">
          <SelectValue placeholder="Select model" />
        </SelectTrigger>
        <SelectContent>
          {models.map((model) => (
            <SelectItem key={model.key} value={model.key}>
              {model.display_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
