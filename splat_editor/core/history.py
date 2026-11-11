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

from abc import ABC, abstracmethod 

class Command(ABC):
    pass 

class DeleteGaussianCommand(Command):
    pass 

class History:
    pass 