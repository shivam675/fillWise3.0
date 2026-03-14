import { useState } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { useNavigate, Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { rulesetsApi } from "@/api/rulesets";
import { extractErrorMessage } from "@/api/client";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";

type RuleForm = {
  id: string;
  name: string;
  instruction: string;
};

type RulesetFormData = {
  name: string;
  version: string;
  description: string;
  jurisdiction: string;
  rules: RuleForm[];
};

export default function RulesetCreatePage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    control,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<RulesetFormData>({
    defaultValues: {
      name: "",
      version: "1.0.0",
      description: "",
      jurisdiction: "",
      rules: [{ id: "", name: "", instruction: "" }],
    },
  });

  const { fields, append, remove } = useFieldArray({
    control,
    name: "rules",
  });

  const createMut = useMutation({
    mutationFn: (data: RulesetFormData) => rulesetsApi.createJson({
      name: data.name,
      version: data.version,
      description: data.description,
      jurisdiction: data.jurisdiction,
      rules: data.rules.map(r => ({
        id: r.id,
        name: r.name,
        instruction: r.instruction
      }))
    } as any),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rulesets"] });
      navigate("/rulesets");
    },
    onError: (err) => setError(extractErrorMessage(err)),
  });

  const onSubmit = (data: RulesetFormData) => {
    setError(null);
    createMut.mutate(data);
  };

  const handleRuleNameChange = (index: number, name: string) => {
    // Only auto-generate ID if it's currently empty, to avoid overwriting user edits
    const currentId = watch(`rules.${index}.id`);
    if (!currentId || currentId === generateId(watch(`rules.${index}.name`))) {
      setValue(`rules.${index}.id`, generateId(name), { shouldValidate: true });
    }
  };

  const generateId = (str: string) => {
    return str
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, "-") // Replace non-alphanumeric with dash
      .replace(/^-+|-+$/g, "");    // Remove leading/trailing dashes
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-20">
      <div className="flex items-center gap-4">
        <Link to="/rulesets" className="p-2 -ml-2 rounded-full hover:bg-gray-100 text-gray-500">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Create Ruleset</h1>
          <p className="text-sm text-gray-500">Manually build a new set of rules</p>
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700 font-medium">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-8">
        <div className="card space-y-4">
          <h2 className="text-lg font-semibold text-gray-900">General Information</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Name <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                {...register("name", { required: "Name is required" })}
                className="input-field"
                placeholder="e.g. Standard Contract Rules"
              />
              {errors.name && <p className="text-xs text-red-500 mt-1">{errors.name.message}</p>}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Version <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                {...register("version", { required: "Version is required" })}
                className="input-field"
                placeholder="e.g. 1.0.0"
              />
              {errors.version && <p className="text-xs text-red-500 mt-1">{errors.version.message}</p>}
            </div>
            
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Jurisdiction
              </label>
              <input
                type="text"
                {...register("jurisdiction")}
                className="input-field"
                placeholder="e.g. New York, federal (optional)"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Description
              </label>
              <textarea
                {...register("description")}
                className="input-field"
                rows={3}
                placeholder="Brief description of what these rules enforce..."
              />
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">Rules</h2>
            <button
              type="button"
              onClick={() => append({ id: "", name: "", instruction: "" })}
              className="btn-secondary text-sm"
            >
              <Plus className="w-4 h-4 mr-1" /> Add Rule
            </button>
          </div>
          
          {errors.rules?.root && (
             <p className="text-sm text-red-500">{errors.rules.root.message}</p>
          )}

          <div className="space-y-4">
            {fields.map((field, index) => (
              <div key={field.id} className="card relative border-l-4 border-l-blue-500">
                {fields.length > 1 && (
                  <button
                    type="button"
                    onClick={() => remove(index)}
                    className="absolute top-4 right-4 text-gray-400 hover:text-red-600 transition-colors"
                  >
                    <Trash2 className="w-5 h-5" />
                  </button>
                )}
                
                <h3 className="font-medium text-gray-800 mb-4">Rule {index + 1}</h3>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4 pr-8">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Rule Name <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      {...register(`rules.${index}.name`, { 
                        required: "Rule name is required",
                        onChange: (e) => handleRuleNameChange(index, e.target.value)
                      })}
                      className="input-field"
                      placeholder="e.g. Remove Passive Voice"
                    />
                    {errors.rules?.[index]?.name && (
                      <p className="text-xs text-red-500 mt-1">{errors.rules[index].name?.message}</p>
                    )}
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Rule ID <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      {...register(`rules.${index}.id`, { required: "Rule ID is required" })}
                      className="input-field font-mono text-sm"
                      placeholder="e.g. remove-passive-voice"
                    />
                    {errors.rules?.[index]?.id && (
                      <p className="text-xs text-red-500 mt-1">{errors.rules[index].id?.message}</p>
                    )}
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Instruction <span className="text-red-500">*</span>
                  </label>
                  <textarea
                    {...register(`rules.${index}.instruction`, { 
                      required: "Instruction is required",
                      minLength: { value: 10, message: "Instruction must be at least 10 characters long" }
                    })}
                    className="input-field font-mono text-sm"
                    rows={4}
                    placeholder="Provide clear LLM instructions for this rule..."
                  />
                  {errors.rules?.[index]?.instruction && (
                    <p className="text-xs text-red-500 mt-1">{errors.rules[index].instruction?.message}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="flex justify-end pt-4 border-t border-gray-200">
          <button
            type="submit"
            className="btn-primary px-8"
            disabled={createMut.isPending}
          >
            {createMut.isPending ? "Creating..." : "Create Ruleset"}
          </button>
        </div>
      </form>
    </div>
  );
}
