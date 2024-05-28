import torch
from torch.utils._python_dispatch import TorchDispatchMode
from . import config
import os
rank = os.getenv("RANK", "0")

cpp_extend = config.get_config("database", "cpp_extend")
if cpp_extend == "True":
    from . import Hook


class Tracer(TorchDispatchMode):
    """
    insert delimiters before and and after op execution
    """

    def __init__(self, model=None, path=None, profiling_bw=False, print_module_info=True, ranks=None) -> None:
        '''
        model: nn.Module or nn.Module list to be traced
        path: path to save profiling data
        profling_bw: whether to profile backward pass, for some specific case, profiling backward pass 
                     will lead to following error: RuntimeError:
                     "Output 0 of BackwardHookFunctionBackward is a view and is being modified inplace.
                     This view was created inside a custom Function (or because an input was returned as-is) 
                     and the autograd logic to handle view+inplace would override the custom backward associated with the custom Function, leading to incorrect gradients. This behavior is forbidden. 
                     You can fix this by cloning the output of the custom Function."
        print_module_info: whether to print module info: e.g. BEGIN FORWARD: {}_froward, END FORWARD: {}_froward, BEGIN BACKWARD: {}_backward, END BACKWARD: {}_backward
        '''
        super().__init__()
        self.profiling_backward = profiling_bw
        self.print_module_info = print_module_info
        self.ranks = ranks
        if self.ranks and rank and int(rank) not in self.ranks:
            return

        # install hooks for some runtime api / fprintf to record time
        Hook.install_hook()

        # enable recorder to record the profiling logs and writo file
        if self.print_module_info:
            Hook.enable_recorder()
            log_path = "/tmp/logs/{}.log".format(rank)
            Hook.set_log_record_path(log_path) 

        # enable timer recording
        Hook.enable_profiling()

        # set path to record profiling data
        if path is None:
            Hook.set_timer_record_path("/tmp/profiling.json")
        else:
            Hook.set_timer_record_path(path)
        
        if model is None:
            return
        else:
            if isinstance(model, list):
                for module in model:
                    m_tuple = self.get_named_modules(module)
                    for name, m, l in m_tuple:
                        self._register_hook(name, m, l)
            elif isinstance(model, torch.nn.Module):
                m_tuple = self.get_named_modules(model)
                for name, m, l in m_tuple:
                    self._register_hook(name, m, l)

    def __exit__(self, exc_type, exc_value, traceback):
        super().__exit__(exc_type, exc_value, traceback)
        Hook.write_to_file()
        Hook.close_recorder()

    def get_named_modules(self, module: torch.nn.Module, prefix=""):
        stack = []
        level = 0
        max_level = 0
        m_name = module.__class__.__name__ if prefix == "" else prefix
        stack.append((m_name, module, level))
        acc_index = 0
        while acc_index < len(stack):
            f_name, f_m, l = stack[acc_index]
            child_modules = f_m.named_children()
            max_level = max(max_level, l)
            counter = 0
            for name, mod in child_modules:
                # construct module name
                if name == "":
                    name = "{}".format(counter)
                    counter += 1
                # store module name and module
                s_name = f_name + "#" + name
                s_m = mod
                stack.append((s_name, s_m, l + 1))

            acc_index += 1
        return stack

    def pre_forward_hook_wrapper(self, name, level):
        def pre_forward_hook(module, input):
            level_name = "Module L{}".format(level)
            if self.print_module_info:
                log_str = "[BEGIN FORWARD]: {}".format(name)
                Hook.record_log(log_str)
            Hook.record_time("B", str(name), level_name)

        return pre_forward_hook

    def post_forward_hook_wrapper(self, name, level):
        def post_forward_hook(module, input, output):
            level_name = "Module L{}".format(level)
            if self.print_module_info:
                log_str = "[END FORWARD]: {}".format(name)
                Hook.record_log(log_str)
            Hook.record_time("E", str(name), level_name)

        return post_forward_hook

    def pre_backward_hook_wrapper(self, name, level):
        def pre_backward_hook(module, input):
            level_name = "Module L{}".format(level)
            if self.print_module_info:
                log_str = "[BEGIN BACKWARD]: {}_backward".format(name)
                Hook.record_log(log_str)
            Hook.record_time("B", str(name), level_name)

        return pre_backward_hook

    def post_backward_hook_wrapper(self, name, level):
        def post_backward_hook(module, input, output):
            level_name = "Module L{}".format(level)
            if self.print_module_info:
                log_str = "[END BACKWARD]: {}_backward".format(name)
                Hook.record_log(log_str)
            Hook.record_time("E", str(name), level_name)

        return post_backward_hook

    def _register_hook(self, name, module, level):
        module.register_forward_pre_hook(self.pre_forward_hook_wrapper(name, level))
        module.register_forward_hook(self.post_forward_hook_wrapper(name, level))

        if self.profiling_backward:
            module.register_full_backward_pre_hook(
                self.pre_backward_hook_wrapper(name, level)
            )
            module.register_full_backward_hook(self.post_backward_hook_wrapper(name, level))

    def __torch_dispatch__(self, op, types, args=(), kwargs=None):
        if kwargs is None:
            kwargs = {}
        if self.print_module_info:
            Hook.record_log("[START_SYMBOL]: {}".format(str(op)))
        Hook.record_time("B", str(op), "aten op")

        # call op
        output = op(*args, **kwargs)

        Hook.record_time("E", str(op), "aten op")
        if self.print_module_info:
            Hook.record_log("[END_SYMBOL]: {}".format(str(op)))
        return output
