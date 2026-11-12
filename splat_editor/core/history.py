"""Lịch sử hoàn tác (undo) theo mẫu Command."""

"""
history = History(max_steps=20)

# Sau khi xoá, đẩy lệnh vào lịch sử (snapshots lấy từ Layer.delete_selected)
snapshots = [(layer, layer.delete_selected())]
history.push(DeleteGaussiansCommand(snapshots))

history.can_undo                        # True
command = history.undo()                # hoàn tác lần xoá gần nhất, trả về Command đã hoàn tác
print(command.description)              # "delete 1,234 gaussians"
history.clear()                         # bỏ hết lịch sử (ví dụ khi mở file mới)

# Muốn thêm thao tác hoàn tác được: kế thừa Command, cài description và undo()
"""

from abc import ABC, abstractmethod


class Command(ABC):
    """Một thao tác đã thực hiện, có thể hoàn tác."""

    @property
    @abstractmethod
    def description(self):
        ...

    @abstractmethod
    def undo(self):
        ...

    def release(self, load):
        """Thay mọi mảng dữ liệu `data` đang giữ bằng load(data) (xem Editor._release_file)."""


class DeleteGaussiansCommand(Command):
    def __init__(self, snapshots):
        self.snapshots = snapshots     # [(lớp, chỉ số các gaussian đã xoá)] (xoá mềm, xem core/layer.py)

    @property
    def count(self):
        """Số gaussian đã xoá."""
        return sum(len(indices) for _, indices in self.snapshots)

    @property
    def description(self):
        return f"delete {self.count:,} gaussians"

    def undo(self):
        for layer, indices in self.snapshots:
            layer.restore(indices)


class History:
    def __init__(self, max_steps=20):
        self.max_steps = max_steps
        self._stack = []

    def __len__(self):
        return len(self._stack)

    def __iter__(self):
        return iter(self._stack)

    @property
    def can_undo(self):
        return bool(self._stack)

    def push(self, command):
        self._stack.append(command)
        del self._stack[:-self.max_steps]

    def undo(self):
        """Hoàn tác thao tác gần nhất. Trả về Command đã hoàn tác hoặc None."""
        if not self._stack:
            return None
        command = self._stack.pop()
        command.undo()
        return command

    def clear(self):
        self._stack.clear()
