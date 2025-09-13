using UnityEngine;
using UnityMeshImporter;

public class ButtonClick : MonoBehaviour
{
    public GameObject meshRoot;

    public void OnButtonClick()
    {
        string meshFile = "Assets/teapot.obj";
        var ob = MeshImporter.Load(meshFile);
        ob.transform.SetParent(meshRoot.transform, false);
    }
}
